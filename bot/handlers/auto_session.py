import asyncio
import logging
import os
import json
import random
import time

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
from services import session_store

logger      = logging.getLogger("auto_session")
router      = Router()

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
SESSIONS_DIR  = os.getenv("SESSIONS_DIR", "/app/sessions")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))

CONCURRENCY = 5

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

_active_tasks: dict = {}


class AutoSessionState(StatesGroup):
    count = State()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _patch_sqlite(client):
    try:
        s = client.session
        if hasattr(s, "_conn") and s._conn:
            s._conn.execute("PRAGMA busy_timeout = 10000")
            s._conn.execute("PRAGMA journal_mode = WAL")
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


# ─── single slot worker ──────────────────────────────────────────────────────────────

async def _buy_one(slot: int) -> tuple[bool, str]:
    """
    Buys ONE valid session. Retries indefinitely until success or cancellation.
    """
    attempt = 0
    logger.info("[slot%d] started", slot)

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
            session_store.remove_files(session_name)

            logger.info("[slot%d] #%d bought %s %s %.3f$",
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
                logger.info("[slot%d] code sent to %s", slot, phone_fmt)
            except PhoneNumberBannedError:
                logger.info("[slot%d] %s banned", slot, phone_fmt)
                await cancel_number(activation_id); continue
            except PhoneNumberInvalidError:
                logger.info("[slot%d] %s invalid", slot, phone_fmt)
                await cancel_number(activation_id); continue
            except FloodWaitError as e:
                logger.info("[slot%d] FloodWait %ds", slot, e.seconds)
                await cancel_number(activation_id)
                await asyncio.sleep(min(e.seconds, 60))
                continue
            except Exception as e:
                logger.warning("[slot%d] send_code err: %s", slot, e)
                await cancel_number(activation_id)
                await asyncio.sleep(5)
                continue

            # 4. wait SMS
            logger.info("[slot%d] waiting SMS for %s...", slot, phone_fmt)
            code = await get_sms_code(activation_id, timeout=90)
            if not code:
                logger.info("[slot%d] no SMS for %s", slot, phone_fmt)
                continue

            logger.info("[slot%d] got code=%s for %s", slot, code, phone_fmt)

            # 5. sign in
            try:
                await asyncio.wait_for(
                    client.sign_in(phone_fmt, code,
                                   phone_code_hash=sent.phone_code_hash),
                    timeout=20,
                )
            except (PhoneCodeExpiredError, PhoneCodeInvalidError):
                logger.info("[slot%d] bad code for %s", slot, phone_fmt)
                await cancel_number(activation_id); continue
            except SessionPasswordNeededError:
                logger.info("[slot%d] 2FA on %s", slot, phone_fmt)
                await cancel_number(activation_id); continue
            except FloodWaitError as e:
                await cancel_number(activation_id)
                await asyncio.sleep(min(e.seconds, 60))
                continue
            except Exception as e:
                logger.warning("[slot%d] sign_in err: %s", slot, e)
                await cancel_number(activation_id)
                await asyncio.sleep(5)
                continue

            # 6. verify
            if not await client.is_user_authorized():
                logger.info("[slot%d] unauthorized after sign_in %s", slot, phone_fmt)
                await cancel_number(activation_id)
                continue

            # 7. get me
            me = await asyncio.wait_for(client.get_me(), timeout=10)
            if not me.first_name:
                await _set_random_profile(client)
                me = await client.get_me()

            # 8. confirm + save
            await confirm_number(activation_id)
            await session_store.save_one(session_name, {
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
            logger.info("[slot%d] cancelled", slot)
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


# ─── parallel buyer ───────────────────────────────────────────────────────────────────

class _Progress:
    """Thread-safe progress tracker."""
    def __init__(self, total: int):
        self.total   = total
        self.done    = 0
        self.success = 0
        self.failed  = 0
        self.results: list[str] = []
        self._lock   = asyncio.Lock()
        self.started_at = time.monotonic()

    async def record(self, ok: bool, desc: str):
        async with self._lock:
            self.done += 1
            self.results.append(desc)
            if ok:
                self.success += 1
            else:
                self.failed += 1

    def active_workers(self) -> int:
        """Estimate active workers = total - done (capped at CONCURRENCY)."""
        return min(self.total - self.done, CONCURRENCY)

    def elapsed(self) -> str:
        s = int(time.monotonic() - self.started_at)
        return f"{s//60}m{s%60:02d}s"


async def _buyer_task(count: int, status_msg, bot, chat_id: int):
    prog = _Progress(count)

    async def worker(slot: int):
        ok, desc = await _buy_one(slot)
        await prog.record(ok, desc)

    async def progress_loop():
        while prog.done < prog.total:
            active = min(prog.total - prog.done, CONCURRENCY)
            try:
                lines = [
                    f"🔄 خرید سشن — {prog.done}/{prog.total}",
                    f"✅ موفق: <b>{prog.success}</b> | "
                    f"❌ ناموفق: <b>{prog.failed}</b>",
                    f"⚡ ورکر فعال: <b>{active}</b> | "
                    f"⏱ {prog.elapsed()}",
                ]
                if prog.results:
                    lines.append("")
                    lines.extend(prog.results[-10:])
                await status_msg.edit_text(
                    "\n".join(lines),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await asyncio.sleep(4)

    logger.info("[buyer] launching %d workers", count)
    workers   = [asyncio.create_task(worker(i + 1)) for i in range(count)]
    prog_task = asyncio.create_task(progress_loop())

    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        for w in workers:
            w.cancel()
        raise
    finally:
        prog_task.cancel()
        try:
            await prog_task
        except asyncio.CancelledError:
            pass

    logger.info("[buyer] done. success=%d failed=%d", prog.success, prog.failed)

    try:
        final_lines = [
            f"🏁 <b>خرید تموم شد!</b>",
            f"✅ موفق: <b>{prog.success}</b> | "
            f"❌ ناموفق: <b>{prog.failed}</b> | "
            f"⏱ {prog.elapsed()}",
            "",
        ] + prog.results
        await bot.send_message(
            chat_id,
            "\n".join(final_lines),
            reply_markup=auto_session_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("[buyer] final send failed: %s", e)


# ─── menu ──────────────────────────────────────────────────────────────────────────────────

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
                   "📊 <b>کشورها (ارزون‌ترین اول):</b>"]
        for cid, p in sorted(prices.items(), key=lambda x: x[1]["cost"]):
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
        f"🚀 شروع خرید <b>{count}</b> سشن\n"
        f"⚡ <b>{CONCURRENCY}</b> ورکر همزمان | ⏹ برای لغو: ‘⏹ لغو خرید’",
        parse_mode="HTML",
    )

    task = asyncio.create_task(
        _buyer_task(count, status_msg, msg.bot, msg.chat.id)
    )
    _active_tasks[msg.from_user.id] = task
