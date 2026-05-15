import glob
import json
import os
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger("warmer_handler")
router = Router()


class ProxyAddState(StatesGroup):
    waiting_for_proxies = State()


PHASE_EMOJI = {
    "new": "🆕",
    "warming": "🔥",
    "warm": "✅",
    "active": "💚"
}


def warmer_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌡 وضعیت گرم‌کردن", callback_data="warm_status"),
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
            InlineKeyboardButton(text="🔙 بازگشت", callback_data="main_menu")
        ]
    ])


@router.message(Command("warmer"))
async def warmer_cmd(msg: Message):
    await msg.answer(
        "🌡 **Session Warmer & Proxy Rotator**\n\n"
        "مدیریت گرم‌کردن سشن‌ها و پروکسی‌های اختصاصی:",
        reply_markup=warmer_menu(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "warm_status")
async def warm_status(cb: CallbackQuery):
    state_files = glob.glob("/app/sessions/.warm_*.json")

    if not state_files:
        await cb.message.edit_text(
            "❌ هیچ سشنی در حال گرم‌کردن نیست.\n"
            "ابتدا سشن اضافه کنید.",
            reply_markup=warmer_menu()
        )
        return

    text = "🌡 **وضعیت گرم‌کردن سشن‌ها:**\n\n"
    for sf in sorted(state_files):
        name = os.path.basename(sf).replace(".warm_", "").replace(".json", "")
        try:
            with open(sf) as f:
                state = json.load(f)
            emoji = PHASE_EMOJI.get(state["phase"], "❓")
            last = state.get("last_active", "نامشخص")
            if last and len(last) > 16:
                last = last[:16]
            text += (
                f"{emoji} `{name}`\n"
                f"   فاز: **{state['phase']}** | روز: {state['day']}\n"
                f"   امتیاز: {state['score']}/20 | اکشن: {state['total_actions']}\n"
                f"   آخرین فعالیت: {last}\n\n"
            )
        except Exception as e:
            text += f"❓ `{name}` - خطا در خواندن\n\n"

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "warm_start")
async def warm_start(cb: CallbackQuery):
    await cb.answer("در حال شروع گرم‌کردن... این فرآیند در پس‌زمینه اجرا می‌شود.", show_alert=True)


@router.callback_query(F.data == "proxy_status")
async def proxy_status(cb: CallbackQuery):
    proxy_file = "/app/data/proxies.json"
    if not os.path.exists(proxy_file):
        await cb.message.edit_text(
            "❌ هیچ پروکسی‌ای ثبت نشده.\n"
            "از دکمه ➕ افزودن پروکسی استفاده کنید.",
            reply_markup=warmer_menu()
        )
        await cb.answer()
        return

    try:
        with open(proxy_file) as f:
            proxies = json.load(f)
        total = len(proxies)
        alive = sum(1 for p in proxies if p.get("is_alive"))
        dead = total - alive
        latencies = [p["latency_ms"] for p in proxies if p.get("is_alive") and p.get("latency_ms", 9999) < 9999]
        avg_lat = sum(latencies) // len(latencies) if latencies else 0

        text = (
            "🔄 **وضعیت پروکسی‌ها:**\n\n"
            f"📊 کل: `{total}`\n"
            f"✅ زنده: `{alive}`\n"
            f"❌ مرده: `{dead}`\n"
            f"⚡ میانگین latency: `{avg_lat}ms`\n"
        )
    except Exception as e:
        text = f"❌ خطا در خواندن پروکسی‌ها: {e}"

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="Markdown")
    await cb.answer()


@router.callback_query(F.data == "proxy_test")
async def proxy_test(cb: CallbackQuery):
    await cb.message.edit_text("🧪 در حال تست پروکسی‌ها... ⏳\nممکن است چند دقیقه طول بکشد.")
    await cb.answer()
    # تست واقعی توسط worker انجام میشه
    # اینجا فقط trigger میفرستیم
    import redis.asyncio as aioredis
    try:
        r = aioredis.from_url("redis://redis:6379")
        await r.lpush("tasks", json.dumps({"type": "test_proxies"}))
        await r.aclose()
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


@router.callback_query(F.data == "proxy_add")
async def proxy_add(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "➕ **افزودن پروکسی**\n\n"
        "پروکسی‌ها رو بفرست (هر خط یکی):\n\n"
        "فرمت‌های قابل قبول:\n"
        "`socks5://user:pass@host:port`\n"
        "`socks5://host:port`\n"
        "`host:port:socks5`\n"
        "`host:port`\n\n"
        "بعد از ارسال، خودکار تست میشن ✅",
        parse_mode="Markdown"
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

    # ذخیره پروکسی‌ها
    proxy_file = "/app/data/proxies.json"
    os.makedirs("/app/data", exist_ok=True)

    existing = []
    if os.path.exists(proxy_file):
        with open(proxy_file) as f:
            existing = json.load(f)

    added = 0
    for line in lines:
        parsed = _parse_proxy_line(line)
        if parsed:
            # چک تکراری نبودن
            if not any(p["host"] == parsed["host"] and p["port"] == parsed["port"] for p in existing):
                existing.append(parsed)
                added += 1

    with open(proxy_file, "w") as f:
        json.dump(existing, f, indent=2)

    await msg.answer(
        f"✅ **{added}** پروکسی جدید اضافه شد!\n"
        f"کل پروکسی‌ها: {len(existing)}\n\n"
        "برای تست از دکمه 🧪 استفاده کنید.",
        reply_markup=warmer_menu(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "warm_full_stats")
async def warm_full_stats(cb: CallbackQuery):
    state_files = glob.glob("/app/sessions/.warm_*.json")
    proxy_file = "/app/data/proxies.json"

    total_sessions = len(state_files)
    warm_count = 0
    warming_count = 0
    total_actions = 0

    for sf in state_files:
        try:
            with open(sf) as f:
                s = json.load(f)
            if s["phase"] in ("warm", "active"):
                warm_count += 1
            elif s["phase"] == "warming":
                warming_count += 1
            total_actions += s.get("total_actions", 0)
        except Exception:
            pass

    proxy_total = 0
    proxy_alive = 0
    if os.path.exists(proxy_file):
        try:
            with open(proxy_file) as f:
                proxies = json.load(f)
            proxy_total = len(proxies)
            proxy_alive = sum(1 for p in proxies if p.get("is_alive"))
        except Exception:
            pass

    text = (
        "📊 **آمار کامل سیستم:**\n\n"
        "🌡 **Session Warmer:**\n"
        f"   کل سشن‌ها: `{total_sessions}`\n"
        f"   ✅ گرم شده: `{warm_count}`\n"
        f"   🔥 در حال گرم‌کردن: `{warming_count}`\n"
        f"   🆕 جدید: `{total_sessions - warm_count - warming_count}`\n"
        f"   کل اکشن‌ها: `{total_actions}`\n\n"
        "🔄 **Proxy Rotator:**\n"
        f"   کل پروکسی‌ها: `{proxy_total}`\n"
        f"   ✅ زنده: `{proxy_alive}`\n"
        f"   ❌ مرده: `{proxy_total - proxy_alive}`\n"
    )

    await cb.message.edit_text(text, reply_markup=warmer_menu(), parse_mode="Markdown")
    await cb.answer()


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
