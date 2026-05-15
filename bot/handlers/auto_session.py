import asyncio
import json
import logging
import os

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, PhoneNumberBannedError

from services.herosms import (
    get_balance, get_cheapest_country, get_number,
    get_sms_code, cancel_number, confirm_number, HeroSMSError
)

logger   = logging.getLogger("auto_session")
router   = Router()

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
SESSIONS_DIR  = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR      = os.getenv("DATA_DIR", "/app/data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))

# Country IDs on HeroSMS (SMS-Activate compatible)
# Preferred countries that work well with Telegram
COUNTRY_LIST = [
    (0,   "🌍 ارزون‌ترین خودکار"),
    (106, "🇰🇿 Kazakhstan"),
    (1,   "🇷🇺 Russia"),
    (14,  "🇺🇦 Ukraine"),
    (6,   "🇮🇩 Indonesia"),
    (22,  "🇵🇭 Philippines"),
    (12,  "🇧🇩 Bangladesh"),
]


class AutoSessionState(StatesGroup):
    country = State()
    count   = State()


def _load_sessions() -> dict:
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE) as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_sessions(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SESSIONS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _patch_sqlite(client):
    try:
        s = client.session
        if hasattr(s, "_conn") and s._conn:
            s._conn.execute("PRAGMA busy_timeout = 10000")
            s._conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass


def auto_session_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 خرید خودکار سشن",  callback_data="autosess_start")],
        [InlineKeyboardButton(text="💰 موجودی HeroSMS",    callback_data="autosess_balance")],
        [InlineKeyboardButton(text="🔙 بازگشت",            callback_data="menu_main")],
    ])


def country_select_kb() -> InlineKeyboardMarkup:
    buttons = []
    for cid, name in COUNTRY_LIST:
        buttons.append([InlineKeyboardButton(
            text=name,
            callback_data=f"autosess_country_{cid}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_autosession")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("autosession"))
async def cmd_autosession(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer(
        "🤖 <b>خرید خودکار سشن</b>\n\n"
        "شماره مجازی از HeroSMS میخره و خودکار Telethon session میسازه.",
        reply_markup=auto_session_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu_autosession")
async def menu_autosession(cb: CallbackQuery):
    await cb.message.edit_text(
        "🤖 <b>خرید خودکار سشن</b>\n\n"
        "شماره مجازی از HeroSMS میخره و خودکار Telethon session میسازه.",
        reply_markup=auto_session_menu(),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(F.data == "autosess_balance")
async def autosess_balance(cb: CallbackQuery):
    await cb.answer()
    try:
        balance = await get_balance()
        await cb.message.edit_text(
            f"💰 <b>موجودی HeroSMS:</b> <code>{balance:.2f}$</code>",
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )
    except HeroSMSError as e:
        await cb.message.edit_text(
            f"❌ خطا در اتصال به HeroSMS:\n<code>{e}</code>",
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "autosess_start")
async def autosess_start(cb: CallbackQuery):
    await cb.answer()
    try:
        balance = await get_balance()
        await cb.message.edit_text(
            f"🤖 <b>خرید سشن تلگرام</b>\n"
            f"💰 موجودی: <code>{balance:.2f}$</code>\n\n"
            f"🌍 کشور مورد نظر رو انتخاب کن:\n"
            f"<i>توصیه: Kazakhstan یا Russia برای سشن باکیفیتتر</i>",
            reply_markup=country_select_kb(),
            parse_mode="HTML",
        )
    except HeroSMSError as e:
        await cb.message.edit_text(
            f"❌ خطا: <code>{e}</code>",
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("autosess_country_"))
async def autosess_country_selected(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cid = int(cb.data.split("_")[-1])

    try:
        if cid == 0:
            # Auto: find cheapest
            country, price = await get_cheapest_country("tg")
        else:
            # Get price for selected country
            from services.herosms import _get
            import aiohttp, json as _json
            async with aiohttp.ClientSession() as sess:
                from services.herosms import HEROSMS_BASE, HEROSMS_API_KEY
                params = {"action": "getPrices", "service": "tg", "country": cid, "api_key": HEROSMS_API_KEY}
                async with sess.get(HEROSMS_BASE, params=params) as r:
                    raw = await r.text()
            try:
                data = _json.loads(raw)
                info = data.get(str(cid), {}).get("tg", {})
                price = float(info.get("cost", 0))
                count_avail = int(info.get("count", 0))
            except Exception:
                price = 0.0
                count_avail = 0
            country = cid

        balance = await get_balance()
        max_possible = int(balance / price) if price > 0 else 0
        country_name = next((n for c, n in COUNTRY_LIST if c == cid), f"Country {cid}")

        await cb.message.edit_text(
            f"🌍 کشور: <b>{country_name}</b> (ID: {country})\n"
            f"💵 قیمت هر شماره: <code>{price:.3f}$</code>\n"
            f"💰 موجودی: <code>{balance:.2f}$</code>\n"
            f"📦 حداکثر قابل خرید: <code>{max_possible}</code> سشن\n\n"
            f"چند سشن میخوای بخری؟ (1-50)",
            parse_mode="HTML",
        )
        await state.set_state(AutoSessionState.count)
        await state.update_data(country=country, price=price)
    except Exception as e:
        await cb.message.edit_text(
            f"❌ خطا: <code>{e}</code>",
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )


@router.message(AutoSessionState.count)
async def autosess_count(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    try:
        count = int(msg.text.strip())
        if count < 1 or count > 50:
            await msg.answer("❌ عدد بین ۱ تا ۵۰ وارد کن.")
            return
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کن.")
        return

    data    = await state.get_data()
    await state.clear()
    country = data["country"]
    price   = data["price"]
    total   = count * price

    status_msg = await msg.answer(
        f"🚀 شروع خرید <b>{count}</b> سشن...\n"
        f"💵 هزینه تخمینی: <code>{total:.2f}$</code>\n\n"
        f"⏳ در حال پردازش...",
        parse_mode="HTML",
    )

    success = 0
    failed  = 0
    results = []

    for i in range(count):
        activation_id = None
        phone         = None
        client        = None
        try:
            # 1. Buy number
            activation_id, phone = await get_number(country, "tg")
            logger.info("[autosess] %d/%d bought %s (id=%d)", i+1, count, phone, activation_id)

            # 2. Connect Telethon
            session_name = phone.lstrip("+")
            session_path = os.path.join(SESSIONS_DIR, session_name)

            # Remove stale session file if exists
            for ext in [".session", ".session-shm", ".session-wal", ".session-journal"]:
                stale = session_path + ext
                if os.path.exists(stale):
                    os.remove(stale)

            client = TelegramClient(session_path, API_ID, API_HASH,
                                    connection_retries=3, retry_delay=2)
            await asyncio.wait_for(client.connect(), timeout=20)
            _patch_sqlite(client)

            # 3. Send code request
            phone_fmt = "+" + phone if not phone.startswith("+") else phone
            sent = await client.send_code_request(phone_fmt)
            logger.info("[autosess] code sent to %s", phone_fmt)

            # 4. Wait for SMS
            await status_msg.edit_text(
                f"📱 [{i+1}/{count}] شماره: <code>{phone_fmt}</code>\n"
                f"⏳ منتظر SMS (حداکثر ۲ دقیقه)...",
                parse_mode="HTML",
            )
            code = await get_sms_code(activation_id, timeout=120)
            logger.info("[autosess] got code=%s for %s", code, phone_fmt)

            if not code:
                await cancel_number(activation_id)
                failed += 1
                results.append(f"❌ {phone_fmt} — SMS نرسید")
                continue

            # 5. Sign in
            try:
                await client.sign_in(phone_fmt, code,
                                     phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                await cancel_number(activation_id)
                failed += 1
                results.append(f"⚠️ {phone_fmt} — 2FA فعاله (skip)")
                continue

            # 6. Verify authorized
            if not await client.is_user_authorized():
                await cancel_number(activation_id)
                failed += 1
                results.append(f"❌ {phone_fmt} — sign_in ناموفق")
                continue

            # 7. Save session
            me = await client.get_me()
            await confirm_number(activation_id)

            sessions_data = _load_sessions()
            sessions_data[session_name] = {
                "phone":    phone_fmt,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
            }
            _save_sessions(sessions_data)

            success += 1
            name_str = f"@{me.username}" if me.username else (me.first_name or "?")
            results.append(f"✅ {phone_fmt} — {name_str}")
            logger.info("[autosess] %s saved OK — %s", session_name, name_str)

        except PhoneNumberBannedError:
            if activation_id:
                await cancel_number(activation_id)
            failed += 1
            results.append(f"🚫 {phone or '?'} — شماره بن شده")
        except FloodWaitError as e:
            if activation_id:
                await cancel_number(activation_id)
            failed += 1
            results.append(f"⏱ {phone or '?'} — FloodWait {e.seconds}s")
            await asyncio.sleep(min(e.seconds, 60))
        except Exception as e:
            if activation_id:
                try:
                    await cancel_number(activation_id)
                except Exception:
                    pass
            failed += 1
            results.append(f"❌ {phone or '?'} — {str(e)[:60]}")
            logger.error("[autosess] error on %s: %s", phone, e, exc_info=True)
        finally:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        await asyncio.sleep(3)

        # Progress update
        try:
            await status_msg.edit_text(
                f"🔄 پیشرفت: {i+1}/{count}\n"
                f"✅ موفق: {success} | ❌ ناموفق: {failed}\n\n"
                + "\n".join(results[-8:]),
                parse_mode="HTML",
            )
        except Exception:
            pass

    # Final report
    await status_msg.edit_text(
        f"🏁 <b>خرید سشن تموم شد!</b>\n\n"
        f"✅ موفق: <b>{success}</b>\n"
        f"❌ ناموفق: <b>{failed}</b>\n\n"
        + "\n".join(results),
        reply_markup=auto_session_menu(),
        parse_mode="HTML",
    )
