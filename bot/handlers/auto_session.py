import asyncio
import logging
import os
import json
import random
from collections import defaultdict

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

# How many sessions to buy in parallel
CONCURRENCY   = 5

COUNTRY_NAMES = {
    106: "🇰🇿 Kazakhstan",
    1:   "🇷🇺 Russia",
    14:  "🇺🇦 Ukraine",
    6:   "🇮🇩 Indonesia",
    22:  "🇵🇭 Philippines",
    12:  "🇧🇩 Bangladesh",
    31:  "🇿🇦 South Africa",
    7:   "🇻🇳 Vietnam",
}

# active buying tasks: admin_id -> asyncio.Task
_active_tasks: dict = {}

# shared progress state per admin
_progress: dict = defaultdict(lambda: {"success": 0, "failed": 0, "results": [], "done": 0})


class AutoSessionState(StatesGroup):
    count = State()


# ─── helpers ──────────────────────────────────────────────────────────────────

_sessions_lock = asyncio.Lock()


def _load_sessions() -> dict:
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE) as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


async def _save_session_safe(session_name: str, info: dict):
    """Thread-safe session save."""
    async with _sessions_lock:
        data = _load_sessions()
        data[session_name] = info
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
        logger.warning("[autosess] set_profile: %s", e)


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


# ─── single session worker ─────────────────────────────────────────────────────────

async def _buy_one(slot: int, total: int, admin_id: int) -> tuple[bool, str]:
    """
    Buy ONE session with unlimited retries until success or cancellation.
    Returns (success, description)
    """
    attempt = 0
    while True:
        attempt += 1
        activation_id = None
        phone         = None
        client        = None

        try:
            # 1. buy number
            try:
                activation_id, phone, country_id, price = await get_number_smart("tg")
            except HeroSMSError as e:
                logger.warning("[slot%d] no numbers: %s — wait 20s", slot, e)
                await asyncio.sleep(20)
                continue

            cname        = COUNTRY_NAMES.get(country_id, f"C{country_id}")
            session_name = phone.lstrip("+")
            session_path = os.path.join(SESSIONS_DIR, session_name)
            phone_fmt    = "+" + phone if not phone.startswith("+") else phone
            _remove_session_files(session_name)

            logger.info("[slot%d] attempt=%d phone=%s %s %.3f$",
                        slot, attempt, phone_fmt, cname, price)

            # 2. connect
            client = TelegramClient(
                session_path, API_ID, API_HASH,
                connection_retries=3, retry_delay=2,
            )
            await asyncio.wait_for(client.connect(), timeout=20)
            _patch_sqlite(client)

            # 3. send code
            try:
                sent = await asyncio.wait_for(
                    client.send_code_request(phone_fmt), timeout=20
                )
            except PhoneNumberBannedError:
                await cancel_number(activation_id)
                continue
            except PhoneNumberInvalidError:
                await cancel_number(activation_id)
                continue
            except FloodWaitError as e:
                await cancel_number(activation_id)
                wait = min(e.seconds, 60)
                logger.info("[slot%d] FloodWait %ds", slot, e.seconds)
                await asyncio.sleep(wait)
                continue

            # 4. wait SMS
            code = await get_sms_code(activation_id, timeout=90)
            if not code:
                # already refunded
                logger.info("[slot%d] no SMS — retry", slot)
                continue

            # 5. sign in
            try:
                await asyncio.wait_for(
                    client.sign_in(phone_fmt, code,
                                   phone_code_hash=sent.phone_code_hash),
                    timeout=20,
                )
            except (PhoneCodeExpiredError, PhoneCodeInvalidError):
                await cancel_number(activation_id)
                continue
            except SessionPasswordNeededError:
                await cancel_number(activation_id)
                continue
            except FloodWaitError as e:
                await cancel_number(activation_id)
                await asyncio.sleep(min(e.seconds, 60))
                continue

            # 6. verify
            if not await client.is_user_authorized():
                await cancel_number(activation_id)
                continue

            # 7. get me
            me = await asyncio.wait_for(client.get_me(), timeout=10)
            if not me.first_name:
                await _set_random_profile(client)
                me = await client.get_me()

            # 8. confirm + save
            await confirm_number(activation_id)
            await _save_session_safe(session_name, {
                "phone":    phone_fmt,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
                "country":  country_id,
                "price":    price,
            })

            name_str = f"@{me.username}" if me.username else (me.first_name or "?")
            logger.info("[slot%d] ✅ %s — %s (attempt %d)", slot, phone_fmt, name_str, attempt)
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
            logger.error("[slot%d] unexpected: %s", slot, e, exc_info=True)
            await asyncio.sleep(5)
        finally:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass


# ─── parallel buyer task ──────────────────────────────────────────────────────────────

async def _buyer_task(count: int, status_msg, bot, chat_id: int, admin_id: int):
    """
    Buys `count` sessions using CONCURRENCY parallel workers.
    Each worker retries indefinitely until it gets one valid session.
    """
    prog = _progress[admin_id]
    prog.update({"success": 0, "failed": 0, "results": [], "done": 0, "total": count})

    # semaphore to limit parallel Telegram connections
    sem = asyncio.Semaphore(CONCURRENCY)

    async def worker(slot: int):
        async with sem:
            ok, desc = await _buy_one(slot, count, admin_id)
            prog["done"]    += 1
            prog["results"].append(desc)
            if ok:
                prog["success"] += 1
            else:
                prog["failed"]  += 1

    # progress updater
    async def progress_loop():
        while prog["done"] < count:
            try:
                await status_msg.edit_text(
                    f"🔄 خرید سشن — {prog['done']}/{count}\n"
                    f"✅ موفق: <b>{prog['success']}</b> | "
                    f"❌ ناموفق: <b>{prog['failed']}</b>\n"
                    f"⚡ همزمان: <b>{CONCURRENCY}</b> ورکر\n\n"
                    + "\n".join(prog["results"][-12:]),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await asyncio.sleep(4)

    # launch all workers + progress loop
    workers = [asyncio.create_task(worker(i + 1)) for i in range(count)]
    prog_task = asyncio.create_task(progress_loop())

    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        for w in workers:
            w.cancel()
        prog_task.cancel()
        raise
    finally:
        prog_task.cancel()

    # final report
    try:
        await bot.send_message(
            chat_id,
            f"🏁 <b>خرید تموم شد!</b>\n\n"
            f"✅ موفق: <b>{prog['success']}</b>\n"
            f"❌ ناموفق: <b>{prog['failed']}</b>\n\n"
            + "\n".join(prog["results"]),
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
                   "📊 <b>کشورهای موجود (ارزون‌ترین اول):</b>"]
        sorted_p = sorted(prices.items(), key=lambda x: x[1]["cost"])
        for cid, p in sorted_p:
            n = COUNTRY_NAMES.get(cid, f"C{cid}")
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
        cname   = COUNTRY_NAMES.get(cid, f"C{cid}")
        max_buy = min(int(balance / price), avail, 50) if price > 0 else 0
        await cb.message.edit_text(
            f"🤖 <b>خرید سشن</b>\n"
            f"💰 موجودی: <code>{balance:.2f}$</code>\n"
            f"🌍 ارزون‌ترین: <b>{cname}</b> — <code>{price:.3f}$</code>\n"
            f"📦 موجود: <code>{avail}</code> | ⚡ همزمان: <b>{CONCURRENCY}</b> ورکر\n"
            f"📊 حداکثر: <code>{max_buy}</code> سشن\n\n"
            f"چند سشن می‌خوای؟ (1–{min(max_buy, 50)})",
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
            "⏹ <b>خرید لغو شد.</b>",
            reply_markup=auto_session_menu(), parse_mode="HTML",
        )
    else:
        await cb.answer("ℹ️ خریدی در جریان نیست.", show_alert=True)


@router.callback_query(F.data == "autosess_cleanup")
async def autosess_cleanup(cb: CallbackQuery):
    await cb.answer()
    msg = await cb.message.edit_text("🔍 در حال بررسی سشن‌ها...", parse_mode="HTML")

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
            removed.append(phone)
        else:
            updated[phone] = info
            kept.append(f"✅ +{phone} — @{info['username'] or info['fullname']}")

    async with _sessions_lock:
        data = {}
        data.update(updated)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SESSIONS_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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

    old = _active_tasks.get(msg.from_user.id)
    if old and not old.done():
        old.cancel()

    status_msg = await msg.answer(
        f"🚀 شروع خرید <b>{count}</b> سشن — ⚡ <b>{CONCURRENCY}</b> ورکر همزمان\n"
        f"⏹ برای لغو: دکمه ‘⏹ لغو خرید’",
        parse_mode="HTML",
    )

    task = asyncio.create_task(
        _buyer_task(count, status_msg, msg.bot, msg.chat.id, msg.from_user.id)
    )
    _active_tasks[msg.from_user.id] = task
