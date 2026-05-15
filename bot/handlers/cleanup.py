"""
Manual session cleanup handler.
Uses session_validator for accurate checks.
Auto-deletes invalid, keeps temp-error sessions.
Paginated results.
"""
import asyncio
import logging
import os

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services import session_store
from services.session_validator import validate_session, INVALID_ERRORS

logger   = logging.getLogger("cleanup")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PAGE_SIZE        = 15
_cleanup_running = False
_last_result: dict = {"valid": [], "deleted": [], "kept_temp": []}


async def run_cleanup(status_msg) -> dict:
    """
    Check all sessions:
    - Permanently invalid (unauthorized, banned, revoked) → auto-delete
    - Temp errors (flood, network) → keep, report
    - Valid → keep, update JSON
    Returns {valid, deleted, kept_temp}
    """
    global _cleanup_running
    if _cleanup_running:
        return _last_result
    _cleanup_running = True

    try:
        keys  = session_store.list_session_files()
        total = len(keys)
        if total == 0:
            return {"valid": [], "deleted": [], "kept_temp": []}

        valid     = []   # info dicts
        deleted   = []   # (key, reason)
        kept_temp = []   # (key, reason)
        done      = 0
        sem       = asyncio.Semaphore(8)
        lock      = asyncio.Lock()

        async def check_one(key: str):
            nonlocal done
            async with sem:
                result = await validate_session(key)
            async with lock:
                done += 1
                if result["ok"]:
                    valid.append(result["info"])
                else:
                    reason = result["reason"]
                    if any(e in reason for e in INVALID_ERRORS):
                        session_store.remove_files(key)
                        deleted.append((key, reason))
                    else:
                        kept_temp.append((key, reason))

                if done % 5 == 0 or done == total:
                    try:
                        await status_msg.edit_text(
                            f"🔍 بررسی سشن‌ها...\n"
                            f"📊 {done}/{total}\n"
                            f"✅ سالم: <b>{len(valid)}</b> | "
                            f"🗑 حذف: <b>{len(deleted)}</b> | "
                            f"⚠️ موقت: <b>{len(kept_temp)}</b>",
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass

        await asyncio.gather(*[check_one(k) for k in keys])

        # Rebuild sessions.json with only valid sessions
        clean = {}
        for info in valid:
            k = info.get("phone", "").lstrip("+")
            if k:
                clean[k] = info
        await session_store.replace_all(clean)

        return {"valid": valid, "deleted": deleted, "kept_temp": kept_temp}

    finally:
        _cleanup_running = False


def _build_text(result: dict, page: int = 0) -> tuple[str, int]:
    valid     = result["valid"]
    deleted   = result["deleted"]
    kept_temp = result["kept_temp"]

    header = [
        f"🧹 <b>پاکسازی تمام شد</b>",
        f"✅ سالم: <b>{len(valid)}</b> | "
        f"🗑 حذف: <b>{len(deleted)}</b> | "
        f"⚠️ موقت: <b>{len(kept_temp)}</b>",
        "",
    ]

    items = []
    for info in valid:
        uname = info.get("username") or info.get("fullname") or "?"
        phone = info.get("phone", "?")
        uid   = info.get("user_id", "")
        items.append(f"✅ <code>{phone}</code> @{uname} <code>{uid}</code>")
    for key, reason in deleted:
        items.append(f"🗑 <code>+{key}</code> — {reason}")
    for key, reason in kept_temp:
        items.append(f"⚠️ <code>+{key}</code> — {reason} (نگه داشته شد)")

    total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page        = max(0, min(page, total_pages - 1))
    chunk       = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    lines = header + chunk
    if total_pages > 1:
        lines.append(f"\n📄 صفحه {page+1}/{total_pages}")

    return "\n".join(lines), total_pages


def _keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
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
        f"🔍 بررسی <b>{len(keys)}</b> سشن — لطفاً صبر کنید...",
        parse_mode="HTML",
    )

    result = await run_cleanup(status_msg)
    _last_result.update(result)

    text, total_pages = _build_text(result, page=0)
    await status_msg.edit_text(
        text,
        reply_markup=_keyboard(0, total_pages),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cleanup_page:"))
async def handle_page(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split(":")[1])
    text, total_pages = _build_text(_last_result, page=page)
    await cb.message.edit_text(
        text,
        reply_markup=_keyboard(page, total_pages),
        parse_mode="HTML",
    )
