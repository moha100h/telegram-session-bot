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

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

PHASE_EMOJI = {
    "new": "🆕",
    "warming": "🔥",
    "warm": "✅",
    "active": "💚"
}


class ProxyAddState(StatesGroup):
    waiting_for_proxies = State()


def warmer_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌡 وضعیت سشن‌ها", callback_data="warm_status"),
            InlineKeyboardButton(text="▶️ شروع دستی", callback_data="warm_start"),
        ],
        [
            InlineKeyboardButton(text="🔄 وضعیت پروکسی", callback_data="proxy_status"),
            InlineKeyboardButton(text="🧪 تست پروکسی‌ها", callback_data="proxy_test"),
        ],
        [
            InlineKeyboardButton(text="➕ افزودن پروکسی", callback_data="proxy_add"),
            InlineKeyboardButton(text="📊 آمار کامل", callback_data="warm_full_stats"),
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main"),
        ]
    ])


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


# --- Entry points ---

@router.message(Command("warmer"))
async def warmer_cmd(msg: Message):
    await msg.answer(
        "🔥 <b>Session Warmer & Proxy Rotator</b>\n\n"
        "مدیریت گرم‌کردن سشن‌ها و پروکسی‌های سیستم:",
        reply_markup=warmer_menu(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu_warmer")
async def menu_warmer(cb: CallbackQuery):
    await cb.message.edit_text(
        "🔥 <b>Session Warmer & Proxy Rotator</b>\n\n"
        "مدیریت گرم‌کردن سشن‌ها و پروکسی‌های سیستم:",
        reply_markup=warmer_menu(),
        parse_mode="HTML"
    )
    await cb.answer()


# --- Warm Status - reads from Redis ---

@router.callback_query(F.data == "warm_status")
async def warm_status(cb: CallbackQuery):
    r = await _get_redis()
    try:
        keys = await r.keys("warm:session:*")
        if not keys:
            await cb.message.edit_text(
                "❌ هیچ سشنی در حال گرم‌کردن نیست.\n"
                "ابتدا سشن اضافه کنید.",
                reply_markup=warmer_menu()
            )
            await cb.answer()
            return

        text = "🌡 <b>وضعیت گرم‌کردن سشن‌ها:</b>\n\n"
        for key in sorted(keys):
            name = key.replace("warm:session:", "")
            try:
                raw = await r.get(key)
                state = json.loads(raw)
                emoji = PHASE_EMOJI.get(state.get("phase", "new"), "❓")
                last = state.get("last_active", "نامشخص")
                if last and len(str(last)) > 16:
                    last = str(last)[:16]
                text += (
                    f"{emoji} <code>{name}</code>\n"
                    f"   فاز: <b>{state.get('phase','?')}</b> | روز: {state.get('day','?')}\n"
                    f"   امتیاز: {state.get('score',0)}/20 | اکشن: {state.get('total_actions',0)}\n"
                    f"   آخرین فعالیت: {last}\n\n"
                )
            except Exception:
                text += f"❓ <code>{name}</code> - خطا در خواندن\n\n"

        await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    finally:
        await r.aclose()
    await cb.answer()


# --- Warm Start ---

@router.callback_query(F.data == "warm_start")
async def warm_start(cb: CallbackQuery):
    r = await _get_redis()
    try:
        await r.lpush("tasks", json.dumps({"type": "start_warming"}))
    finally:
        await r.aclose()
    await cb.answer("✅ دستور شروع گرم‌کردن ارسال شد!", show_alert=True)


# --- Proxy Status - reads from Redis ---

@router.callback_query(F.data == "proxy_status")
async def proxy_status(cb: CallbackQuery):
    r = await _get_redis()
    try:
        raw = await r.get("proxies:list")
        if not raw:
            await cb.message.edit_text(
                "❌ هیچ پروکسی‌ای ثبت نشده.\n"
                "از دکمه ➕ افزودن پروکسی استفاده کنید.",
                reply_markup=warmer_menu()
            )
            await cb.answer()
            return

        proxies = json.loads(raw)
        total = len(proxies)
        alive = sum(1 for p in proxies if p.get("is_alive"))
        dead = total - alive
        latencies = [p["latency_ms"] for p in proxies if p.get("is_alive") and p.get("latency_ms", 9999) < 9999]
        avg_lat = sum(latencies) // len(latencies) if latencies else 0

        text = (
            "🔄 <b>وضعیت پروکسی‌ها:</b>\n\n"
            f"📊 کل: <code>{total}</code>\n"
            f"✅ زنده: <code>{alive}</code>\n"
            f"❌ مرده: <code>{dead}</code>\n"
            f"⚡ میانگین latency: <code>{avg_lat}ms</code>\n"
        )
    except Exception as e:
        text = f"❌ خطا در خواندن پروکسی‌ها: {e}"
    finally:
        await r.aclose()

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="HTML")
    await cb.answer()


# --- Proxy Test ---

@router.callback_query(F.data == "proxy_test")
async def proxy_test(cb: CallbackQuery):
    r = await _get_redis()
    try:
        await r.lpush("tasks", json.dumps({"type": "test_proxies"}))
        await cb.message.edit_text(
            "✅ دستور تست پروکسی‌ها ارسال شد!\n"
            "نتیجه چند دقیقه دیگر در لاگ‌ها قابل مشاهده است.",
            reply_markup=warmer_menu()
        )
    except Exception as e:
        await cb.message.edit_text(
            f"❌ خطا در ارسال دستور: {e}",
            reply_markup=warmer_menu()
        )
    finally:
        await r.aclose()
    await cb.answer()


# --- Proxy Add ---

@router.callback_query(F.data == "proxy_add")
async def proxy_add(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "➕ <b>افزودن پروکسی</b>\n\n"
        "پروکسی‌ها رو بفرست (هر خط یکی):\n\n"
        "فرمت‌های قابل قبول:\n"
        "<code>socks5://user:pass@host:port</code>\n"
        "<code>socks5://host:port</code>\n"
        "<code>host:port:socks5</code>\n"
        "<code>host:port</code>\n\n"
        "بعد از ارسال، خودکار تست میشن ✅",
        parse_mode="HTML"
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
    try:
        raw = await r.get("proxies:list")
        existing = json.loads(raw) if raw else []

        added = 0
        for line in lines:
            parsed = _parse_proxy_line(line)
            if parsed:
                if not any(p["host"] == parsed["host"] and p["port"] == parsed["port"] for p in existing):
                    existing.append(parsed)
                    added += 1

        await r.set("proxies:list", json.dumps(existing))
        await r.lpush("tasks", json.dumps({"type": "test_proxies"}))
    finally:
        await r.aclose()

    await msg.answer(
        f"✅ <b>{added}</b> پروکسی جدید اضافه شد!\n"
        f"کل پروکسی‌ها: {len(existing)}\n\n"
        "برای تست از دکمه 🧪 استفاده کنید.",
        reply_markup=warmer_menu(),
        parse_mode="HTML"
    )


# --- Full Stats - reads sessions + proxies from Redis ---

@router.callback_query(F.data == "warm_full_stats")
async def warm_full_stats(cb: CallbackQuery):
    r = await _get_redis()
    try:
        keys = await r.keys("warm:session:*")
        total_sessions = len(keys)
        warm_count = warming_count = total_actions = 0
        for key in keys:
            try:
                raw = await r.get(key)
                s = json.loads(raw)
                phase = s.get("phase", "new")
                if phase in ("warm", "active"):
                    warm_count += 1
                elif phase == "warming":
                    warming_count += 1
                total_actions += s.get("total_actions", 0)
            except Exception:
                pass

        proxy_total = proxy_alive = 0
        raw_p = await r.get("proxies:list")
        if raw_p:
            try:
                proxies = json.loads(raw_p)
                proxy_total = len(proxies)
                proxy_alive = sum(1 for p in proxies if p.get("is_alive"))
            except Exception:
                pass

        session_keys = await r.keys("session:*")
        total_system_sessions = len(session_keys)

    finally:
        await r.aclose()

    text = (
        "📊 <b>آمار کامل سیستم:</b>\n\n"
        "📱 <b>سشن‌های سیستم:</b>\n"
        f"   کل: <code>{total_system_sessions}</code>\n\n"
        "🌡 <b>Session Warmer:</b>\n"
        f"   کل: <code>{total_sessions}</code>\n"
        f"   ✅ گرم شده: <code>{warm_count}</code>\n"
        f"   🔥 در حال گرم‌کردن: <code>{warming_count}</code>\n"
        f"   🆕 جدید: <code>{total_sessions - warm_count - warming_count}</code>\n"
        f"   کل اکشن‌ها: <code>{total_actions}</code>\n\n"
        "🔄 <b>Proxy Rotator:</b>\n"
        f"   کل: <code>{proxy_total}</code>\n"
        f"   ✅ زنده: <code>{proxy_alive}</code>\n"
        f"   ❌ مرده: <code>{proxy_total - proxy_alive}</code>\n"
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
            return {"host": host, "port": int(port), "type": ptype,
                    "username": user, "password": passwd,
                    "latency_ms": 9999, "fail_count": 0,
                    "last_checked": 0.0, "is_alive": False}
        else:
            parts = raw.split(":")
            if len(parts) >= 2:
                return {"host": parts[0], "port": int(parts[1]),
                        "type": parts[2] if len(parts) > 2 else "socks5",
                        "username": "", "password": "",
                        "latency_ms": 9999, "fail_count": 0,
                        "last_checked": 0.0, "is_alive": False}
    except Exception:
        pass
    return None
