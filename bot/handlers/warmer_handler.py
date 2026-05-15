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
TASK_QUEUE   = "tsb:task_queue"

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
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_session_files() -> list:
    names = []
    if os.path.exists(SESSIONS_DIR):
        for fn in os.listdir(SESSIONS_DIR):
            if fn.endswith(".session"):
                names.append(fn.replace(".session", ""))
    return sorted(names)


# --- Entry points ---

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


# --- Warm Status ---

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

    r = await _get_redis()
    try:
        text = "🌡 <b>وضعیت سشن‌ها:</b>\n\n"
        for name in session_files:
            meta     = sessions_meta.get(name, {})
            phone    = meta.get("phone", "+" + name)
            fullname = meta.get("fullname", "").strip()
            verified = meta.get("verified", False)

            warm_raw = await r.get("warm:session:" + name)
            if warm_raw:
                try:
                    ws        = json.loads(warm_raw)
                    emoji     = PHASE_EMOJI.get(ws.get("phase", "new"), "❓")
                    last      = str(ws.get("last_active", "نامشخص"))[:16]
                    fname_part = (" (" + fullname + ")") if fullname else ""
                    proxy_info = ws.get("proxy_host", "مستقیم")
                    text += (
                        emoji + " <code>" + phone + "</code>" + fname_part + "\n"
                        "   فاز: <b>" + ws.get("phase", "?") + "</b> | "
                        "روز: " + str(ws.get("day", "?")) + " | "
                        "امتیاز: " + str(ws.get("score", 0)) + "/20\n"
                        "   آخرین فعالیت: " + last + "\n"
                        "   🔄 پروکسی: <code>" + str(proxy_info) + "</code>\n\n"
                    )
                except Exception:
                    text += "❓ <code>" + phone + "</code> - خطا در خواندن\n\n"
            else:
                icon       = "✅" if verified else "🆕"
                v_icon     = "✅" if verified else "❌"
                fname_part = (" (" + fullname + ")") if fullname else ""
                text += (
                    icon + " <code>" + phone + "</code>" + fname_part + "\n"
                    "   فاز: جدید (گرم نشده) | تایید: " + v_icon + "\n\n"
                )
    finally:
        await r.aclose()

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# --- Warm Start ---

@router.callback_query(F.data == "warm_start")
async def warm_start(cb: CallbackQuery):
    r = await _get_redis()
    try:
        await r.lpush(TASK_QUEUE, json.dumps({"type": "start_warming"}))
    finally:
        await r.aclose()
    await cb.answer("✅ دستور شروع گرم‌کردن به worker ارسال شد!", show_alert=True)


# --- Proxy Status ---

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

        # Read proxy test result if available
        test_raw = await r.get("tsb:proxy_test_result")
        test_info = ""
        if test_raw:
            try:
                tr = json.loads(test_raw)
                test_info = (
                    "\n\n🧪 <b>آخرین تست:</b>\n"
                    "   ✅ زنده: <code>" + str(tr.get("alive", "?")) + "/" + str(tr.get("tested", "?")) + "</code>\n"
                    "   ⏱ میانگین پینگ: <code>" + str(tr.get("avg_ping_ms", "?")) + "ms</code>\n"
                    "   ⏰ زمان: " + str(tr.get("ts", ""))[:16]
                )
            except Exception:
                pass

        samples = []
        for i in range(min(3, total)):
            raw = await r.lindex("tsb:proxies", i)
            try:
                samples.append(json.loads(raw))
            except Exception:
                pass

        types_count = {}
        for s in samples:
            t = s.get("type", "unknown")
            types_count[t] = types_count.get(t, 0) + 1
        types_str = ", ".join(t + ": " + str(c) for t, c in types_count.items())
        first = samples[0] if samples else {}

        text = (
            "🔄 <b>وضعیت پروکسی‌ها:</b>\n\n"
            "📊 کل: <code>" + str(total) + "</code>\n"
            "🔍 نمونه: <code>" + str(first.get("host", "?")) + ":" + str(first.get("port", "?")) + "</code>\n"
            "🏷 نوع: <code>" + types_str + "</code>\n"
            "⏰ آپدیت خودکار هر ساعت توسط proxy_fetcher"
            + test_info
        )
    except Exception as e:
        text = "❌ خطا: " + str(e)
    finally:
        await r.aclose()

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# --- Proxy Test ---

@router.callback_query(F.data == "proxy_test")
async def proxy_test(cb: CallbackQuery):
    r = await _get_redis()
    try:
        await r.lpush(TASK_QUEUE, json.dumps({"type": "test_proxies"}))
        await cb.message.edit_text(
            "✅ دستور تست پروکسی‌ها به worker ارسال شد!\n"
            "نتیجه در <b>وضعیت پروکسی</b> قابل مشاهده خواهد بود.",
            reply_markup=warmer_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        await cb.message.edit_text("❌ خطا: " + str(e), reply_markup=warmer_menu())
    finally:
        await r.aclose()
    await cb.answer()


# --- Proxy Add ---

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
        "✅ <b>" + str(added) + "</b> پروکسی جدید به لیست اضافه شد!\n"
        "کل پروکسی‌ها: <code>" + str(total) + "</code>",
        reply_markup=warmer_menu(),
        parse_mode="HTML",
    )


# --- Full Stats ---

@router.callback_query(F.data == "warm_full_stats")
async def warm_full_stats(cb: CallbackQuery):
    session_files  = _get_session_files()
    sessions_meta  = _load_sessions_file()
    total_sessions = len(session_files)
    verified_count = sum(1 for n in session_files if sessions_meta.get(n, {}).get("verified"))

    r = await _get_redis()
    try:
        warm_count = warming_count = total_actions = 0
        for name in session_files:
            raw = await r.get("warm:session:" + name)
            if raw:
                try:
                    s     = json.loads(raw)
                    phase = s.get("phase", "new")
                    if phase in ("warm", "active"):
                        warm_count += 1
                    elif phase == "warming":
                        warming_count += 1
                    total_actions += s.get("total_actions", 0)
                except Exception:
                    pass

        proxy_total = await r.llen("tsb:proxies")

        # Proxy test result
        test_raw = await r.get("tsb:proxy_test_result")
        proxy_alive = "?"
        proxy_ping  = "?"
        if test_raw:
            try:
                tr = json.loads(test_raw)
                proxy_alive = str(tr.get("alive", "?")) + "/" + str(tr.get("tested", "?"))
                proxy_ping  = str(tr.get("avg_ping_ms", "?")) + "ms"
            except Exception:
                pass
    finally:
        await r.aclose()

    not_verified = total_sessions - verified_count
    not_warmed   = total_sessions - warm_count - warming_count

    text = (
        "📊 <b>آمار کامل سیستم:</b>\n\n"
        "📱 <b>سشن‌ها:</b>\n"
        "   کل: <code>" + str(total_sessions) + "</code>\n"
        "   ✅ تایید شده: <code>" + str(verified_count) + "</code>\n"
        "   ❌ تایید نشده: <code>" + str(not_verified) + "</code>\n\n"
        "🔥 <b>Session Warmer:</b>\n"
        "   ✅ گرم شده: <code>" + str(warm_count) + "</code>\n"
        "   🔥 در حال گرم‌کردن: <code>" + str(warming_count) + "</code>\n"
        "   🆕 جدید: <code>" + str(not_warmed) + "</code>\n"
        "   📊 کل اکشن‌ها: <code>" + str(total_actions) + "</code>\n\n"
        "🔄 <b>Proxy Rotator:</b>\n"
        "   📊 کل: <code>" + str(proxy_total) + "</code>\n"
        "   ✅ زنده (آخرین تست): <code>" + proxy_alive + "</code>\n"
        "   ⏱ میانگین پینگ: <code>" + proxy_ping + "</code>\n"
        "   ⏰ آپدیت خودکار هر ساعت"
    )

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# --- Helper ---

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
