"""
Professional session cleanup handler.
- Scans all .session files on disk
- Connects each via Telethon and checks authorization
- Removes invalid ones atomically (file + JSON)
- Deduplicates: each phone processed exactly once
- Paginated results in Telegram
- Runs in background so bot stays responsive
"""
import asyncio
import logging
import os
import time

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient

from services import session_store

logger   = logging.getLogger("cleanup")
router   = Router()

API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Prevent concurrent cleanups
_cleanup_running = False

PAGE_SIZE = 20


# ─── core verify ────────────────────────────────────────────────────────────────────

async def _check_one(key: str) -> dict | None:
    """
    Connect to session, verify auth, return enriched info or None.
    None means invalid — should be deleted.
    """
    path   = os.path.join(session_store.SESSIONS_DIR, key)
    client = TelegramClient(path, API_ID, API_HASH,
                            connection_retries=1, retry_delay=1)
    try:
        await asyncio.wait_for(client.connect(), timeout=12)

        # WAL mode for SQLite
        try:
            s = client.session
            if hasattr(s, "_conn") and s._conn:
                s._conn.execute("PRAGMA busy_timeout=5000")
                s._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

        if not await asyncio.wait_for(client.is_user_authorized(), timeout=8):
            return None

        me = await asyncio.wait_for(client.get_me(), timeout=8)
        if not me:
            return None

        phone_fmt = "+" + key if not key.startswith("+") else key
        return {
            "phone":    phone_fmt,
            "verified": True,
            "username": me.username or "",
            "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
            "user_id":  me.id,
            "dc_id":    getattr(getattr(me, "photo", None), "dc_id", None),
        }
    except asyncio.TimeoutError:
        logger.warning("[cleanup] timeout: %s", key)
        return None
    except Exception as e:
        logger.warning("[cleanup] error %s: %s", key, e)
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


# ─── background cleanup task ──────────────────────────────────────────────────────────────

async def run_cleanup(status_msg) -> tuple[list, list]:
    """
    Full cleanup:
    1. Deduplicate session file list
    2. Check each one (parallel, max 5 at a time)
    3. Remove invalid ones atomically
    4. Rebuild sessions.json from scratch
    Returns (kept_list, removed_list)
    """
    global _cleanup_running
    if _cleanup_running:
        return [], []
    _cleanup_running = True

    try:
        keys = session_store.list_session_files()  # deduped
        total = len(keys)
        logger.info("[cleanup] found %d unique session files", total)

        if total == 0:
            return [], []

        kept    = {}   # key -> info
        removed = []   # keys
        done    = 0
        sem     = asyncio.Semaphore(5)  # max 5 parallel checks
        lock    = asyncio.Lock()

        async def check_and_decide(key: str):
            nonlocal done
            async with sem:
                info = await _check_one(key)
            async with lock:
                done += 1
                if info is None:
                    session_store.remove_files(key)
                    removed.append(key)
                    logger.info("[cleanup] ❌ removed %s", key)
                else:
                    kept[key] = info
                    logger.info("[cleanup] ✅ valid %s — %s",
                                key, info.get("username") or info.get("fullname"))

                # progress update every 5
                if done % 5 == 0 or done == total:
                    try:
                        await status_msg.edit_text(
                            f"🔍 بررسی سشن‌ها...\n"
                            f"📊 {done}/{total} بررسی شد\n"
                            f"✅ معتبر: <b>{len(kept)}</b> | "
                            f"🗑 نامعتبر: <b>{len(removed)}</b>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        await asyncio.gather(*[check_and_decide(k) for k in keys])

        # Rebuild sessions.json atomically from scratch
        await session_store.replace_all(kept)
        logger.info("[cleanup] done. kept=%d removed=%d", len(kept), len(removed))

        return list(kept.values()), removed

    finally:
        _cleanup_running = False


# ─── paginated result builder ──────────────────────────────────────────────────────────────

def _build_result_text(kept: list, removed: list, page: int = 0) -> tuple[str, int]:
    """
    Build paginated result text.
    Returns (text, total_pages)
    """
    lines = [
        f"🧹 <b>پاکسازی تمام شد</b>\n",
        f"✅ معتبر: <b>{len(kept)}</b> | "
        f"🗑 حذف شده: <b>{len(removed)}</b>\n",
    ]

    all_items = []
    for info in kept:
        uname = info.get("username") or info.get("fullname") or "?"
        phone = info.get("phone", "?")
        uid   = info.get("user_id", "")
        all_items.append(f"✅ <code>{phone}</code> — @{uname} (<code>{uid}</code>)")
    for key in removed:
        all_items.append(f"🗑 <code>+{key}</code> — حذف شد")

    total_pages = max(1, (len(all_items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(0, min(page, total_pages - 1))
    start       = page * PAGE_SIZE
    chunk       = all_items[start:start + PAGE_SIZE]

    lines.extend(chunk)
    if total_pages > 1:
        lines.append(f"\n📄 صفحه {page+1}/{total_pages}")

    return "\n".join(lines), total_pages


def _result_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"cleanup_page:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"cleanup_page:{page+1}"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🧹 پاکسازی مجدد", callback_data="autosess_cleanup")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت",         callback_data="menu_autosession")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── cache last result for pagination ──────────────────────────────────────────────────────────────

_last_result: dict = {"kept": [], "removed": []}


# ─── handlers ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "autosess_cleanup")
async def handle_cleanup(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️ دسترسی ندارید.", show_alert=True)
        return

    if _cleanup_running:
        await cb.answer("⏳ پاکسازی در حال اجراست...", show_alert=True)
        return

    await cb.answer()
    keys = session_store.list_session_files()
    status_msg = await cb.message.edit_text(
        f"🔍 بررسی <b>{len(keys)}</b> سشن بصورت همزمان...\n"
        f"⏳ لطفاً صبر کنید.",
        parse_mode="HTML",
    )

    kept, removed = await run_cleanup(status_msg)
    _last_result["kept"]    = kept
    _last_result["removed"] = removed

    text, total_pages = _build_result_text(kept, removed, page=0)
    await status_msg.edit_text(
        text,
        reply_markup=_result_keyboard(0, total_pages),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cleanup_page:"))
async def handle_cleanup_page(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split(":")[1])
    kept    = _last_result.get("kept", [])
    removed = _last_result.get("removed", [])
    text, total_pages = _build_result_text(kept, removed, page=page)
    await cb.message.edit_text(
        text,
        reply_markup=_result_keyboard(page, total_pages),
        parse_mode="HTML",
    )
