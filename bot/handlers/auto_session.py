import asyncio
import json
import logging
import os
import random
import string

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError,
    PhoneNumberBannedError, PhoneCodeExpiredError,
    PhoneCodeInvalidError, PhoneNumberInvalidError,
)

from services.herosms import (
    get_balance, get_prices, get_best_country,
    get_number_smart, get_sms_code,
    cancel_number, confirm_number, HeroSMSError,
    PREFERRED_COUNTRIES,
)

logger       = logging.getLogger("auto_session")
router       = Router()

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
SESSIONS_DIR  = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR      = os.getenv("DATA_DIR", "/app/data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))

COUNTRY_NAMES = {
    0:   "🌍 ارزون‌ترین خودکار",
    106: "🇰🇿 Kazakhstan",
    1:   "🇷🇺 Russia",
    14:  "🇺🇦 Ukraine",
    6:   "🇮🇩 Indonesia",
    22:  "🇵🇭 Philippines",
    12:  "🇧🇩 Bangladesh",
    31:  "🇿🇦 South Africa",
}


class AutoSessionState(StatesGroup):
    count = State()


# ─── helpers ────────────────────────────────────────────────────────────────

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


def _remove_session_files(phone: str):
    """Remove all .session files for a phone number."""
    base = os.path.join(SESSIONS_DIR, phone)
    for ext in [".session", ".session-shm", ".session-wal", ".session-journal"]:
        p = base + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


async def _verify_and_enrich(phone: str) -> dict | None:
    """
    Connect to existing session, verify it's authorized,
    and return enriched info dict or None if invalid.
    """
    session_path = os.path.join(SESSIONS_DIR, phone)
    client = TelegramClient(session_path, API_ID, API_HASH,
                            connection_retries=2, retry_delay=2)
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
        _patch_sqlite(client)

        if not await client.is_user_authorized():
            return None

        me = await asyncio.wait_for(client.get_me(), timeout=10)
        if not me:
            return None

        # Set profile if missing
        first = me.first_name or ""
        last  = me.last_name  or ""
        uname = me.username   or ""

        return {
            "phone":    "+" + phone if not phone.startswith("+") else phone,
            "verified": True,
            "username": uname,
            "fullname": (first + " " + last).strip(),
            "user_id":  me.id,
            "dc_id":    me.photo.dc_id if me.photo else None,
        }
    except Exception as e:
        logger.warning("[autosess] verify %s failed: %s", phone, e)
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def _set_random_profile(client: TelegramClient):
    """Set a random first/last name if account has no name."""
    try:
        me = await client.get_me()
        if me and not me.first_name:
            first_names = ["Alex", "Sam", "Jordan", "Taylor", "Morgan",
                           "Casey", "Riley", "Jamie", "Avery", "Quinn"]
            last_names  = ["Smith", "Johnson", "Brown", "Davis", "Wilson",
                           "Moore", "Taylor", "Anderson", "Thomas", "Jackson"]
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            await client("account.UpdateProfileRequest", first_name=fn, last_name=ln)
            logger.info("[autosess] set profile: %s %s", fn, ln)
    except Exception as e:
        logger.warning("[autosess] set_profile failed: %s", e)


# ─── menus ──────────────────────────────────────────────────────────────────

def auto_session_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 خرید خودکار سشن",    callback_data="autosess_start")],
        [InlineKeyboardButton(text="🧹 پاکسازی سشن‌های نامعتبر", callback_data="autosess_cleanup")],
        [InlineKeyboardButton(text="💰 موجودی HeroSMS",       callback_data="autosess_balance")],
        [InlineKeyboardButton(text="🔙 بازگشت",               callback_data="menu_main")],
    ])


# ─── handlers ───────────────────────────────────────────────────────────────

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
    await cb.answer()
    await cb.message.edit_text(
        "🤖 <b>خرید خودکار سشن</b>\n\n"
        "شماره مجازی از HeroSMS میخره و خودکار Telethon session میسازه.",
        reply_markup=auto_session_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "autosess_balance")
async def autosess_balance(cb: CallbackQuery):
    await cb.answer()
    try:
        balance = await get_balance()
        # Also show available countries
        prices = await get_prices("tg")
        lines = [f"💰 <b>موجودی HeroSMS:</b> <code>{balance:.2f}$</code>\n"]
        lines.append("📊 <b>کشورهای موجود:</b>")
        for cid in PREFERRED_COUNTRIES:
            if cid in prices:
                name = COUNTRY_NAMES.get(cid, f"Country {cid}")
                p    = prices[cid]
                lines.append(f"  {name}: <code>{p['cost']:.3f}$</code> ({p['count']} عدد)")
        await cb.message.edit_text(
            "\n".join(lines),
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )
    except HeroSMSError as e:
        await cb.message.edit_text(
            f"❌ خطا: <code>{e}</code>",
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "autosess_start")
async def autosess_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    try:
        balance = await get_balance()
        cid, price, avail = await get_best_country("tg")
        country_name = COUNTRY_NAMES.get(cid, f"Country {cid}")
        max_possible = min(int(balance / price), avail, 50) if price > 0 else 0

        await cb.message.edit_text(
            f"🤖 <b>خرید سشن تلگرام</b>\n"
            f"💰 موجودی: <code>{balance:.2f}$</code>\n"
            f"🌍 بهترین کشور: <b>{country_name}</b> (ID: {cid})\n"
            f"💵 قیمت هر شماره: <code>{price:.3f}$</code>\n"
            f"📦 موجود: <code>{avail}</code> شماره\n"
            f"📊 حداکثر قابل خرید: <code>{max_possible}</code> سشن\n\n"
            f"چند سشن می‌خوای بخری؟ (1-{min(max_possible, 50)})",
            parse_mode="HTML",
        )
        await state.set_state(AutoSessionState.count)
        await state.update_data(country=cid, price=price)
    except HeroSMSError as e:
        await cb.message.edit_text(
            f"❌ خطا در اتصال به HeroSMS:\n<code>{e}</code>",
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "autosess_cleanup")
async def autosess_cleanup(cb: CallbackQuery):
    await cb.answer()
    msg = await cb.message.edit_text(
        "🔍 در حال بررسی سشن‌ها...\nلطفاً صبر کنید.",
        parse_mode="HTML",
    )

    sessions_data = _load_sessions()
    session_files = [
        f.replace(".session", "")
        for f in os.listdir(SESSIONS_DIR)
        if f.endswith(".session") and not f.endswith("-shm") and not f.endswith("-wal")
    ]

    removed   = []
    kept      = []
    updated   = {}

    for phone in session_files:
        info = await _verify_and_enrich(phone)
        if info is None:
            _remove_session_files(phone)
            if phone in sessions_data:
                del sessions_data[phone]
            removed.append(phone)
            logger.info("[cleanup] removed invalid session: %s", phone)
        else:
            updated[phone] = info
            kept.append(f"✅ +{phone} — @{info['username'] or info['fullname']}")

    # Also remove from sessions.json entries that have no file
    for phone in list(sessions_data.keys()):
        if phone not in updated:
            del sessions_data[phone]

    sessions_data.update(updated)
    _save_sessions(sessions_data)

    lines = [f"🧹 <b>پاکسازی تمام شد!</b>\n"]
    lines.append(f"✅ معتبر: <b>{len(kept)}</b>")
    lines.append(f"🗑 حذف شده: <b>{len(removed)}</b>\n")
    if kept:
        lines.append("<b>سشن‌های معتبر:</b>")
        lines.extend(kept[:20])
    if removed:
        lines.append("\n<b>حذف شده‌ها:</b>")
        lines.extend([f"❌ +{p}" for p in removed[:20]])

    await msg.edit_text(
        "\n".join(lines),
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

    data  = await state.get_data()
    await state.clear()

    status_msg = await msg.answer(
        f"🚀 شروع خرید <b>{count}</b> سشن...\n⏳ در حال پردازش...",
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
            # 1. Buy number (smart — tries best countries)
            activation_id, phone, country_id, price = await get_number_smart("tg")
            cname = COUNTRY_NAMES.get(country_id, f"C{country_id}")
            logger.info("[autosess] %d/%d bought %s id=%d (%s)", i+1, count, phone, activation_id, cname)

            # 2. Prepare session path
            session_name = phone.lstrip("+")
            session_path = os.path.join(SESSIONS_DIR, session_name)
            _remove_session_files(session_name)  # clean stale

            # 3. Connect Telethon
            client = TelegramClient(
                session_path, API_ID, API_HASH,
                connection_retries=3, retry_delay=3,
            )
            await asyncio.wait_for(client.connect(), timeout=20)
            _patch_sqlite(client)

            # 4. Send code
            phone_fmt = "+" + phone if not phone.startswith("+") else phone
            sent = await asyncio.wait_for(
                client.send_code_request(phone_fmt), timeout=20
            )

            # 5. Update progress
            await status_msg.edit_text(
                f"📱 [{i+1}/{count}] شماره: <code>{phone_fmt}</code> ({cname})\n"
                f"⏳ منتظر SMS (حداکثر ۲ دقیقه)...",
                parse_mode="HTML",
            )

            # 6. Wait for SMS
            code = await get_sms_code(activation_id, timeout=120)

            if not code:
                failed += 1
                results.append(f"❌ {phone_fmt} — SMS نرسید (refund شد)")
                continue

            # 7. Sign in
            try:
                await asyncio.wait_for(
                    client.sign_in(phone_fmt, code, phone_code_hash=sent.phone_code_hash),
                    timeout=20,
                )
            except PhoneCodeExpiredError:
                await cancel_number(activation_id)
                failed += 1
                results.append(f"❌ {phone_fmt} — کد منقضی شد (refund)")
                continue
            except PhoneCodeInvalidError:
                await cancel_number(activation_id)
                failed += 1
                results.append(f"❌ {phone_fmt} — کد اشتباه (refund)")
                continue
            except SessionPasswordNeededError:
                await cancel_number(activation_id)
                failed += 1
                results.append(f"⚠️ {phone_fmt} — 2FA فعاله (refund)")
                continue

            # 8. Verify
            if not await client.is_user_authorized():
                await cancel_number(activation_id)
                failed += 1
                results.append(f"❌ {phone_fmt} — unauthorized بعد از sign_in (refund)")
                continue

            # 9. Get full user info
            me = await asyncio.wait_for(client.get_me(), timeout=10)

            # 10. Set random profile if no name
            if me and not me.first_name:
                await _set_random_profile(client)
                me = await client.get_me()  # refresh

            # 11. Confirm purchase
            await confirm_number(activation_id)

            # 12. Save to sessions.json
            sessions_data = _load_sessions()
            sessions_data[session_name] = {
                "phone":    phone_fmt,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
                "country":  country_id,
                "price":    price,
            }
            _save_sessions(sessions_data)

            success += 1
            name_str = f"@{me.username}" if me.username else (me.first_name or "?")
            results.append(f"✅ {phone_fmt} — {name_str} ({cname})")
            logger.info("[autosess] saved %s — %s", session_name, name_str)

        except PhoneNumberBannedError:
            if activation_id:
                await cancel_number(activation_id)
            failed += 1
            results.append(f"🚫 {phone or '?'} — شماره بن شده (refund)")
        except PhoneNumberInvalidError:
            if activation_id:
                await cancel_number(activation_id)
            failed += 1
            results.append(f"❌ {phone or '?'} — شماره نامعتبر (refund)")
        except FloodWaitError as e:
            if activation_id:
                await cancel_number(activation_id)
            failed += 1
            wait = min(e.seconds, 60)
            results.append(f"⏱ {phone or '?'} — FloodWait {e.seconds}s (refund)")
            await asyncio.sleep(wait)
        except HeroSMSError as e:
            failed += 1
            results.append(f"❌ ? — {str(e)[:60]}")
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

        await asyncio.sleep(2)

        # Progress update
        try:
            await status_msg.edit_text(
                f"🔄 پیشرفت: {i+1}/{count}\n"
                f"✅ موفق: {success} | ❌ ناموفق: {failed}\n\n"
                + "\n".join(results[-10:]),
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
