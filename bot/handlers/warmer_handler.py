import json
import logging
import os

import redis.asyncio as aioredis
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger("warmer_handler")
router = Router()

REDIS_URL    = os.getenv("REDIS_URL", "redis://redis:6379/0")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")

PHASE_EMOJI = {
    "new":     "🆕",
    "warming": "🔥",
    "warm":    "✅",
    "active":  "💚",
}


class ProxyAddState(StatesGroup):
    waiting_for_proxies = State()


def warmer_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌡 وضعیت سشن‌ها",   callback_data="warm_status"),
            InlineKeyboardButton(text="▶️ شروع دستی",    callback_data="warm_start"),
        ],
        [
            InlineKeyboardButton(text="🔄 وضعیت پروکسی",  callback_data="proxy_status"),
            InlineKeyboardButton(text="🧪 تست پروکسی‌ها", callback_data="proxy_test"),
        ],
        [
            InlineKeyboardButton(text="➕ افزودن پروکسی",  callback_data="proxy_add"),
            InlineKeyboardButton(text="📊 آمار کامل",      callback_data="warm_full_stats"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"),
        ],
    ])


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


def _load_sessions_file() -> dict:
    """Read sessions.json from disk (same source as session_manager)"""
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_session_files() -> list:
    """List .session files on disk"""
    names = []
    if os.path.exists(SESSIONS_DIR):
        for fn in os.listdir(SESSIONS_DIR):
            if fn.endswith(".session"):
                names.append(fn.replace(".session", ""))
    return sorted(names)


# ─── Entry points ─────────────────────────────────────────────────────────────

@router.message(Command("warmer"))
async def warmer_cmd(msg: Message):
    await msg.answer(
        "🔥 <b>Session Warmer & Proxy Rotator</b>\n\n"
        "مدیریت گرم‌کردن سشن‌ها و پروکسی‌های سیستم:",
        reply_markup=warmer_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu_warmer")
async def menu_warmer(cb: CallbackQuery):
    await cb.message.edit_text(
        "🔥 <b>Session Warmer & Proxy Rotator</b>\n\n"
        "مدیریت گرم‌کردن سشن‌ها و پروکسی‌های سیستم:",
        reply_markup=warmer_menu(),
        parse_mode="HTML",
    )
    await cb.answer()


# ─── Warm Status — reads from sessions.json + .session files ──────────────────

@router.callback_query(F.data == "warm_status")
async def warm_status(cb: CallbackQuery):
    session_files = _get_session_files()
    sessions_meta = _load_sessions_file()

    if not session_files:
        await cb.message.edit_text(
            "❌ هیچ سشنی در سیستم وجود ندارد.\n"
            "ابتدا از بخش 📱 سشن‌ها سشن اضافه کنید.",
            reply_markup=warmer_menu(),
        )
        await cb.answer()
        return

    # Read warm states from Redis (warm:session:<name>)
    r = await _get_redis()
    try:
        text = "🌡 <b>وضعیت سشن‌ها:</b>\n\n"
        for name in session_files:
            meta = sessions_meta.get(name, {})
            phone    = meta.get("phone", "+" + name)
            fullname = meta.get("fullname", "").strip()
            verified = meta.get("verified", False)

            # warm state from Redis if exists
            warm_raw = await r.get(f"warm:session:{name}")
            if warm_raw:
                try:
                    ws = json.loads(warm_raw)
                    emoji = PHASE_EMOJI.get(ws.get("phase", "new"), "❓")
                    last  = str(ws.get("last_active", "نامشخص"))[:16]
                    text += (
                        f"{emoji} <code>{phone}</code>"
                        + (f" ({fullname})" if fullname else "") + "\n"
                        f"   فاز: <b>{ws.get('phase','?')}</b> | "
                        f"روز: {ws.get('day','?')} | "
                        f"امتیاز: {ws.get('score',0)}/20\n"
                        f"   آخرین فعالیت: {last}\n\n"
                    )
                except Exception:
                    text += f"❓ <code>{phone}</code> - خطا در خواندن\n\n"
            else:
                icon = "✅" if verified else "🆕"
                text += (
                    f"{icon} <code>{phone}</code>"
                    + (f" ({fullname})" if fullname else "") + "\n"
                    f"   فاز: جدید (گرم نشده) | تایید: {'\u2705' if verified else '\u274c'}\n\n"
                )
    finally:
        await r.aclose()

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# ─── Warm Start ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "warm_start")
async def warm_start(cb: CallbackQuery):
    r = await _get_redis()
    try:
        await r.lpush("tasks", json.dumps({"type": "start_warming"}))
    finally:
        await r.aclose()
    await cb.answer("✅ دستور شروع گرم‌کردن ارسال شد!", show_alert=True)


# ─── Proxy Status — reads from tsb:proxies (Redis list) ───────────────────────

@router.callback_query(F.data == "proxy_status")
async def proxy_status(cb: CallbackQuery):
    r = await _get_redis()
    try:
        total = await r.llen("tsb:proxies")
        if total == 0:
            await cb.message.edit_text(
                "❌ هیچ پروکسی‌ای در سیستم نیست.\n"
                "پروکسی‌ها توسط proxy_fetcher هر ساعت آپدیت میشن.",
                reply_markup=warmer_menu(),
            )
            await cb.answer()
            return

        # Sample first 5 to show types
        samples = []
        for i in range(min(5, total)):
            raw = await r.lindex("tsb:proxies", i)
            try:
                samples.append(json.loads(raw))
            except Exception:
                pass

        types_count = {}
        for s in samples:
            t = s.get("type", "unknown")
            types_count[t] = types_count.get(t, 0) + 1

        types_str = ", ".join(f"{t}: {c}" for t, c in types_count.items())

        text = (
            "🔄 <b>وضعیت پروکسی‌ها:</b>\n\n"
            f"📊 کل پروکسی: <code>{total}</code>\n"
            f"🔍 نمونه اول: <code>{samples[0].get('host','?')}:{samples[0].get('port','?')}</code>\n"
            f"🏷 نوع: <code>{types_str}</code>\n\n"
            f"⏰ آپدیت خودکار توسط proxy_fetcher هر ساعت"
        )
    except Exception as e:
        text = f"❌ خطا: {e}"
    finally:
        await r.aclose()

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# ─── Proxy Test ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "proxy_test")
async def proxy_test(cb: CallbackQuery):
    r = await _get_redis()
    try:
        await r.lpush("tasks", json.dumps({"type": "test_proxies"}))
        await cb.message.edit_text(
            "✅ دستور تست پروکسی‌ها به worker ارسال شد!\n"
            "نتیجه در لاگ‌ها قابل مشاهده است.",
            reply_markup=warmer_menu(),
        )
    except Exception as e:
        await cb.message.edit_text(f"❌ خطا: {e}", reply_markup=warmer_menu())
    finally:
        await r.aclose()
    await cb.answer()


# ─── Proxy Add — appends to tsb:proxies list ──────────────────────────────────

@router.callback_query(F.data == "proxy_add")
async def proxy_add(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "➕ <b>افزودن پروکسی دستی</b>\n\n"
        "پروکسی‌ها رو بفرست (هر خط یکی):\n\n"
        "فرمت‌های قابل قبول:\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>socks5://host:port</code>\n"
        "<code>host:port:socks5</code>\n"
        "<code>host:port</code>\n\n"
        "در کنار پروکسی‌های proxy_fetcher (هر ساعت آپدیت) به لیست اضافه میشن ✅",
        parse_mode="HTML",
    )
    await state.set_state(ProxyAddState.waiting_for_proxies)
    await cb.answer()


@router.message(ProxyAddState.waiting_for_proxies)
async def receive_proxies(msg: Message, state: FSMContext):
    await state.clear()
    lines = [l.strip() for l in msg.text.strip().splitlines() if l.strip()]

    if not lines:
        await msg.answer("❌ هیچ پروکسی‌ای دریافت نشد.", reply_markup=warmer_menu())
        return

    r = await _get_redis()
    added = 0
    try:
        for line in lines:
            parsed = _parse_proxy_line(line)
            if parsed:
                await r.rpush("tsb:proxies", json.dumps(parsed))
                added += 1
        total = await r.llen("tsb:proxies")
    finally:
        await r.aclose()

    await msg.answer(
        f"✅ <b>{added}</b> پروکسی جدید به لیست اضافه شد!\n"
        f"کل پروکسی‌ها: <code>{total}</code>",
        reply_markup=warmer_menu(),
        parse_mode="HTML",
    )


# ─── Full Stats ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "warm_full_stats")
async def warm_full_stats(cb: CallbackQuery):
    # Sessions from file
    session_files  = _get_session_files()
    sessions_meta  = _load_sessions_file()
    total_sessions = len(session_files)
    verified_count = sum(1 for n in session_files if sessions_meta.get(n, {}).get("verified"))

    # Warm states from Redis
    r = await _get_redis()
    try:
        warm_count = warming_count = total_actions = 0
        for name in session_files:
            raw = await r.get(f"warm:session:{name}")
            if raw:
                try:
                    s = json.loads(raw)
                    phase = s.get("phase", "new")
                    if phase in ("warm", "active"):
                        warm_count += 1
                    elif phase == "warming":
                        warming_count += 1
                    total_actions += s.get("total_actions", 0)
                except Exception:
                    pass

        proxy_total = await r.llen("tsb:proxies")
    finally:
        await r.aclose()

    text = (
        "📊 <b>آمار کامل سیستم:</b>\n\n"
        "📱 <b>سشن‌های سیستم:</b>\n"
        f"   کل: <code>{total_sessions}</code>\n"
        f"   ✅ تایید شده: <code>{verified_count}</code>\n"
        f"   ❌ تایید نشده: <code>{total_sessions - verified_count}</code>\n\n"
        "🌡 <b>Session Warmer:</b>\n"
        f"   ✅ گرم شده: <code>{warm_count}</code>\n"
        f"   🔥 در حال گرم‌کردن: <code>{warming_count}</code>\n"
        f"   🆕 جدید (گرم نشده): <code>{total_sessions - warm_count - warming_count}</code>\n"
        f"   کل اکشن‌ها: <code>{total_actions}</code>\n\n"
        "🔄 <b>Proxy Rotator:</b>\n"
        f"   کل پروکسی: <code>{proxy_total}</code>\n"
        f"   ⏰ آپدیت خودکار هر ساعت توسط proxy_fetcher"
    )

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# ─── Helper ────────────────────────────────────────────────────────────────────

def _parse_proxy_line(raw: str) -> dict | None:
    try:
        raw = raw.strip()
        if not raw:
            return None
        if "://" in raw:
            ptype, rest = raw.split("://", 1)
            if "@" in rest:
                auth, hostport = rest.rsplit("@", 1)
                user, passwd = auth.split(":", 1)
            else:
                hostport = rest
                user = passwd = ""
            host, port = hostport.rsplit(":", 1)
            return {"type": ptype, "host": host, "port": port,
                    "username": user, "password": passwd}
        else:
            parts = raw.split(":")
            if len(parts) >= 2:
                return {"type": parts[2] if len(parts) > 2 else "socks5",
                        "host": parts[0], "port": parts[1],
                        "username": "", "password": ""}
    except Exception:
        pass
    return None
