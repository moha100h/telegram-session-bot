import asyncio
import logging
import os
import json
import random

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

logger      = logging.getLogger("auto_session")
router      = Router()

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
SESSIONS_DIR  = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR      = os.getenv("DATA_DIR", "/app/data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))

COUNTRY_NAMES = {
    0:   "🌍 خودکار",
    106: "🇰🇿 Kazakhstan",
    1:   "🇷🇺 Russia",
    14:  "🇺🇦 Ukraine",
    6:   "🇮🇩 Indonesia",
    22:  "🇵🇭 Philippines",
    12:  "🇧🇩 Bangladesh",
    31:  "🇿🇦 South Africa",
}

# active buying tasks: admin_id -> asyncio.Task
_active_tasks: dict[int, asyncio.Task] = {}


class AutoSessionState(StatesGroup):
    count = State()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _load_sessions() -> dict:
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE) as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
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
    base = os.path.join(SESSIONS_DIR, phone)
    for ext in [".session", ".session-shm", ".session-wal", ".session-journal"]:
        p = base + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


async def _set_random_profile(client: TelegramClient):
    try:
        me = await client.get_me()
        if me and not me.first_name:
            fn = random.choice(["Alex","Sam","Jordan","Taylor","Morgan",
                                "Casey","Riley","Jamie","Avery","Quinn"])
            ln = random.choice(["Smith","Johnson","Brown","Davis","Wilson",
                                "Moore","Taylor","Anderson","Thomas","Jackson"])
            from telethon.tl.functions.account import UpdateProfileRequest
            await client(UpdateProfileRequest(first_name=fn, last_name=ln))
    except Exception as e:
        logger.warning("[autosess] set_profile failed: %s", e)


async def _verify_and_enrich(phone: str) -> dict | None:
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
        return {
            "phone":    "+" + phone if not phone.startswith("+") else phone,
            "verified": True,
            "username": me.username or "",
            "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
            "user_id":  me.id,
        }
    except Exception as e:
        logger.warning("[autosess] verify %s: %s", phone, e)
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


# ─── core buyer loop ──────────────────────────────────────────────────────────

async def _buy_one_session(attempt_num: int, total: int, status_msg) -> tuple[bool, str]:
    """
    Try to buy and create ONE valid session.
    Retries internally on NO_NUMBERS, bad SMS, etc.
    Returns (success: bool, description: str)
    """
    MAX_INNER_RETRIES = 10  # retries per single slot
    inner = 0

    while inner < MAX_INNER_RETRIES:
        inner += 1
        activation_id = None
        phone         = None
        client        = None

        try:
            # ── 1. buy number (smart country picker) ──
            try:
                activation_id, phone, country_id, price = await get_number_smart("tg")
            except HeroSMSError as e:
                # No numbers anywhere — wait and retry
                logger.warning("[autosess] no numbers (try %d): %s", inner, e)
                await asyncio.sleep(15)
                continue

            cname        = COUNTRY_NAMES.get(country_id, f"C{country_id}")
            session_name = phone.lstrip("+")
            session_path = os.path.join(SESSIONS_DIR, session_name)
            _remove_session_files(session_name)

            phone_fmt = "+" + phone if not phone.startswith("+") else phone

            # ── 2. connect telethon ──
            client = TelegramClient(
                session_path, API_ID, API_HASH,
                connection_retries=3, retry_delay=3,
            )
            await asyncio.wait_for(client.connect(), timeout=20)
            _patch_sqlite(client)

            # ── 3. send code ──
            try:
                sent = await asyncio.wait_for(
                    client.send_code_request(phone_fmt), timeout=20
                )
            except PhoneNumberBannedError:
                await cancel_number(activation_id)
                logger.info("[autosess] %s banned, refund, retry", phone_fmt)
                continue
            except PhoneNumberInvalidError:
                await cancel_number(activation_id)
                continue
            except FloodWaitError as e:
                await cancel_number(activation_id)
                wait = min(e.seconds, 120)
                logger.info("[autosess] FloodWait %ds", e.seconds)
                await asyncio.sleep(wait)
                continue

            # ── 4. update status ──
            try:
                await status_msg.edit_text(
                    f"🔄 سشن {attempt_num}/{total}\n"
                    f"📱 شماره: <code>{phone_fmt}</code> ({cname})\n"
                    f"⏳ منتظر SMS... (تلاش {inner}/{MAX_INNER_RETRIES})",
                    parse_mode="HTML",
                )
            except Exception:
                pass

            # ── 5. wait for SMS ──
            code = await get_sms_code(activation_id, timeout=120)

            if not code:
                # already refunded inside get_sms_code
                logger.info("[autosess] no SMS for %s, retry", phone_fmt)
                continue

            # ── 6. sign in ──
            try:
                await asyncio.wait_for(
                    client.sign_in(phone_fmt, code,
                                   phone_code_hash=sent.phone_code_hash),
                    timeout=20,
                )
            except PhoneCodeExpiredError:
                await cancel_number(activation_id)
                continue
            except PhoneCodeInvalidError:
                await cancel_number(activation_id)
                continue
            except SessionPasswordNeededError:
                await cancel_number(activation_id)
                logger.info("[autosess] 2FA on %s, refund, retry", phone_fmt)
                continue
            except FloodWaitError as e:
                await cancel_number(activation_id)
                await asyncio.sleep(min(e.seconds, 120))
                continue

            # ── 7. verify ──
            if not await client.is_user_authorized():
                await cancel_number(activation_id)
                continue

            # ── 8. get user info ──
            me = await asyncio.wait_for(client.get_me(), timeout=10)

            # ── 9. set profile if missing ──
            if me and not me.first_name:
                await _set_random_profile(client)
                me = await client.get_me()

            # ── 10. confirm purchase ──
            await confirm_number(activation_id)

            # ── 11. save ──
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

            name_str = f"@{me.username}" if me.username else (me.first_name or "?")
            logger.info("[autosess] ✅ saved %s — %s", session_name, name_str)
            return True, f"✅ {phone_fmt} — {name_str} ({cname})"

        except asyncio.CancelledError:
            if activation_id:
                try:
                    await cancel_number(activation_id)
                except Exception:
                    pass
            raise
        except Exception as e:
            if activation_id:
                try:
                    await cancel_number(activation_id)
                except Exception:
                    pass
            logger.error("[autosess] unexpected: %s", e, exc_info=True)
            await asyncio.sleep(5)
            continue
        finally:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    return False, f"❌ سشن {attempt_num} — پس از {MAX_INNER_RETRIES} تلاش ناموفق"


async def _buyer_task(count: int, status_msg, bot, chat_id: int):
    """Main background task: buys `count` sessions, fully automatic."""
    success = 0
    failed  = 0
    results = []

    for i in range(count):
        if asyncio.current_task().cancelled():
            break

        ok, desc = await _buy_one_session(i + 1, count, status_msg)
        if ok:
            success += 1
        else:
            failed += 1
        results.append(desc)

        # progress
        try:
            await status_msg.edit_text(
                f"🔄 پیشرفت: {i+1}/{count}\n"
                f"✅ موفق: {success} | ❌ ناموفق: {failed}\n\n"
                + "\n".join(results[-10:]),
                parse_mode="HTML",
            )
        except Exception:
            pass

        await asyncio.sleep(2)

    # final
    try:
        await bot.send_message(
            chat_id,
            f"🏁 <b>خرید سشن تموم شد!</b>\n\n"
            f"✅ موفق: <b>{success}</b>\n"
            f"❌ ناموفق: <b>{failed}</b>\n\n"
            + "\n".join(results),
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─── menus ────────────────────────────────────────────────────────────────────

def auto_session_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 خرید خودکار سشن",       callback_data="autosess_start")],
        [InlineKeyboardButton(text="⏹ لغو خرید",               callback_data="autosess_cancel")],
        [InlineKeyboardButton(text="🧹 پاکسازی سشن‌های نامعتبر",  callback_data="autosess_cleanup")],
        [InlineKeyboardButton(text="💰 موجودی HeroSMS",          callback_data="autosess_balance")],
        [InlineKeyboardButton(text="🔙 بازگشت",                  callback_data="menu_main")],
    ])


# ─── handlers ─────────────────────────────────────────────────────────────────

@router.message(Command("autosession"))
async def cmd_autosession(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer(
        "🤖 <b>خرید خودکار سشن</b>\n"
        "شماره مجازی از HeroSMS میخره و خودکار session میسازه.",
        reply_markup=auto_session_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "menu_autosession")
async def menu_autosession(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text(
        "🤖 <b>خرید خودکار سشن</b>\n"
        "شماره مجازی از HeroSMS میخره و خودکار session میسازه.",
        reply_markup=auto_session_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "autosess_balance")
async def autosess_balance(cb: CallbackQuery):
    await cb.answer()
    try:
        balance = await get_balance()
        prices  = await get_prices("tg")
        lines   = [f"💰 <b>موجودی:</b> <code>{balance:.2f}$</code>\n",
                   "📊 <b>کشورهای موجود:</b>"]
        for cid in PREFERRED_COUNTRIES:
            if cid in prices:
                n = COUNTRY_NAMES.get(cid, f"C{cid}")
                p = prices[cid]
                lines.append(f"  {n}: <code>{p['cost']:.3f}$</code> ({p['count']} عدد)")
        await cb.message.edit_text("\n".join(lines),
                                   reply_markup=auto_session_menu(), parse_mode="HTML")
    except HeroSMSError as e:
        await cb.message.edit_text(f"❌ {e}", reply_markup=auto_session_menu(), parse_mode="HTML")


@router.callback_query(F.data == "autosess_start")
async def autosess_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    try:
        balance = await get_balance()
        cid, price, avail = await get_best_country("tg")
        cname       = COUNTRY_NAMES.get(cid, f"C{cid}")
        max_buy     = min(int(balance / price), avail, 50) if price > 0 else 0
        await cb.message.edit_text(
            f"🤖 <b>خرید سشن</b>\n"
            f"💰 موجودی: <code>{balance:.2f}$</code>\n"
            f"🌍 بهترین کشور: <b>{cname}</b>\n"
            f"💵 قیمت: <code>{price:.3f}$</code> | موجود: <code>{avail}</code>\n"
            f"📦 حداکثر: <code>{max_buy}</code> سشن\n\n"
            f"چند سشن می‌خوای؟ (1–{min(max_buy,50)})",
            parse_mode="HTML",
        )
        await state.set_state(AutoSessionState.count)
    except HeroSMSError as e:
        await cb.message.edit_text(f"❌ {e}", reply_markup=auto_session_menu(), parse_mode="HTML")


@router.callback_query(F.data == "autosess_cancel")
async def autosess_cancel(cb: CallbackQuery):
    await cb.answer()
    task = _active_tasks.get(cb.from_user.id)
    if task and not task.done():
        task.cancel()
        await cb.message.edit_text(
            "⏹ <b>خرید لغو شد.</b>\nسشن‌های خریداری شده حفظ می‌مانن.",
            reply_markup=auto_session_menu(), parse_mode="HTML",
        )
    else:
        await cb.message.edit_text(
            "ℹ️ خریدی در جریان نیست.",
            reply_markup=auto_session_menu(), parse_mode="HTML",
        )


@router.callback_query(F.data == "autosess_cleanup")
async def autosess_cleanup(cb: CallbackQuery):
    await cb.answer()
    msg = await cb.message.edit_text("🔍 در حال بررسی سشن‌ها...", parse_mode="HTML")

    sessions_data = _load_sessions()
    session_files = [
        f.replace(".session", "")
        for f in os.listdir(SESSIONS_DIR)
        if f.endswith(".session")
    ]

    removed = []
    updated = {}
    kept    = []

    for phone in session_files:
        info = await _verify_and_enrich(phone)
        if info is None:
            _remove_session_files(phone)
            sessions_data.pop(phone, None)
            removed.append(phone)
        else:
            updated[phone] = info
            kept.append(f"✅ +{phone} — @{info['username'] or info['fullname']}")

    for phone in list(sessions_data.keys()):
        if phone not in updated:
            sessions_data.pop(phone, None)

    sessions_data.update(updated)
    _save_sessions(sessions_data)

    lines = [f"🧹 <b>پاکسازی تمام شد!</b>\n",
             f"✅ معتبر: <b>{len(kept)}</b> | 🗑 حذف: <b>{len(removed)}</b>\n"]
    lines += kept[:20]
    if removed:
        lines.append("\n<b>حذف شده:</b>")
        lines += [f"❌ +{p}" for p in removed[:20]]

    await msg.edit_text("\n".join(lines), reply_markup=auto_session_menu(), parse_mode="HTML")


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

    await state.clear()

    # cancel previous task if running
    old = _active_tasks.get(msg.from_user.id)
    if old and not old.done():
        old.cancel()

    status_msg = await msg.answer(
        f"🚀 شروع خرید <b>{count}</b> سشن خودکار...\n"
        f"🔄 تا زمانی که همه سشن‌ها ساخته نشن، ادامه می‌دهد.\n"
        f"⏹ برای لغو دکمه ‘⏹ لغو خرید’ را بزن.",
        parse_mode="HTML",
    )

    task = asyncio.create_task(
        _buyer_task(count, status_msg, msg.bot, msg.chat.id)
    )
    _active_tasks[msg.from_user.id] = task
