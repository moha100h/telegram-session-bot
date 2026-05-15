import asyncio
import logging
import os
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
)
from services import session_store

logger   = logging.getLogger("auto_session")
router   = Router()

API_ID       = int(os.getenv("API_ID", "0"))
API_HASH     = os.getenv("API_HASH", "")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "0"))

CONCURRENCY = 5

COUNTRY_NAMES = {
    106: "🇰🇿 KZ", 1: "🇷🇺 RU", 14: "🇺🇦 UA",
    6:   "🇮🇩 ID", 22: "🇵🇭 PH", 12: "🇧🇩 BD",
    31:  "🇿🇦 ZA", 7:  "🇻🇳 VN",
}

SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

_active_tasks: dict = {}
# slot_status[admin_id][slot] = status string
_slot_status: dict = {}


class AutoSessionState(StatesGroup):
    count = State()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _patch_sqlite(client):
    try:
        s = client.session
        if hasattr(s, "_conn") and s._conn:
            s._conn.execute("PRAGMA busy_timeout=10000")
            s._conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass


async def _set_random_profile(client):
    try:
        me = await client.get_me()
        if me and not me.first_name:
            from telethon.tl.functions.account import UpdateProfileRequest
            fn = random.choice(["Alex","Sam","Jordan","Taylor","Morgan",
                                "Casey","Riley","Jamie","Avery","Quinn"])
            ln = random.choice(["Smith","Johnson","Brown","Davis","Wilson",
                                "Moore","Taylor","Anderson","Thomas","Jackson"])
            await client(UpdateProfileRequest(first_name=fn, last_name=ln))
    except Exception as e:
        logger.warning("set_profile: %s", e)


# ─── Progress tracker ──────────────────────────────────────────────────────────────────

class Progress:
    def __init__(self, total: int):
        self.total      = total
        self.done       = 0
        self.success    = 0
        self.failed     = 0
        self.results:   list[str] = []
        # per-slot live status
        self.slots:     dict[int, str] = {}
        self._lock      = asyncio.Lock()
        self.started_at = time.monotonic()
        self._spin_i    = 0

    async def set_slot(self, slot: int, status: str):
        async with self._lock:
            self.slots[slot] = status

    async def record(self, slot: int, ok: bool, desc: str):
        async with self._lock:
            self.done += 1
            self.results.append(desc)
            self.slots.pop(slot, None)  # slot finished
            if ok:
                self.success += 1
            else:
                self.failed += 1

    def spin(self) -> str:
        self._spin_i = (self._spin_i + 1) % len(SPINNER)
        return SPINNER[self._spin_i]

    def elapsed(self) -> str:
        s = int(time.monotonic() - self.started_at)
        return f"{s//60}m{s%60:02d}s"

    def render(self) -> str:
        sp    = self.spin()
        lines = [
            f"{sp} <b>خرید سشن</b> — {self.done}/{self.total}",
            f"✅ موفق: <b>{self.success}</b>  "
            f"❌ ناموفق: <b>{self.failed}</b>  "
            f"⏱ {self.elapsed()}",
        ]
        # live slot statuses
        if self.slots:
            lines.append("")
            lines.append("⚡ <b>ورکرهای فعال:</b>")
            for slot in sorted(self.slots):
                lines.append(f"  • سلات {slot}: {self.slots[slot]}")
        # last results
        if self.results:
            lines.append("")
            lines.extend(self.results[-8:])
        return "\n".join(lines)


# ─── single slot worker ──────────────────────────────────────────────────────────────

async def _buy_one(slot: int, prog: Progress) -> tuple[bool, str]:
    attempt = 0
    logger.info("[slot%d] started", slot)
    await prog.set_slot(slot, "⏳ شروع...")

    while True:
        attempt += 1
        activation_id = None
        phone         = None
        client        = None
        try:
            # 1. buy number
            await prog.set_slot(slot, "🛍 خرید شماره...")
            try:
                activation_id, phone, country_id, price = await get_number_smart("tg")
            except HeroSMSError as e:
                await prog.set_slot(slot, f"❌ نه شماره — صبر 20s")
                logger.warning("[slot%d] no numbers: %s", slot, e)
                await asyncio.sleep(20)
                continue

            cname     = COUNTRY_NAMES.get(country_id, f"C{country_id}")
            sname     = phone.lstrip("+")
            spath     = os.path.join(SESSIONS_DIR, sname)
            phone_fmt = "+" + phone if not phone.startswith("+") else phone
            session_store.remove_files(sname)

            logger.info("[slot%d] #%d %s %s %.3f$", slot, attempt, phone_fmt, cname, price)
            await prog.set_slot(slot, f"📱 {phone_fmt} ({cname})")

            # 2. connect
            client = TelegramClient(spath, API_ID, API_HASH,
                                    connection_retries=3, retry_delay=2)
            await asyncio.wait_for(client.connect(), timeout=20)
            _patch_sqlite(client)

            # 3. send code
            await prog.set_slot(slot, f"📨 ارسال کد → {phone_fmt}")
            try:
                sent = await asyncio.wait_for(
                    client.send_code_request(phone_fmt), timeout=20)
            except PhoneNumberBannedError:
                await prog.set_slot(slot, f"🚫 بن شده — بعدی")
                await cancel_number(activation_id); continue
            except PhoneNumberInvalidError:
                await prog.set_slot(slot, f"❌ شماره نامعتبر — بعدی")
                await cancel_number(activation_id); continue
            except FloodWaitError as e:
                await prog.set_slot(slot, f"⏳ FloodWait {e.seconds}s")
                await cancel_number(activation_id)
                await asyncio.sleep(min(e.seconds, 60)); continue
            except Exception as e:
                await prog.set_slot(slot, f"⚠️ {str(e)[:30]}")
                await cancel_number(activation_id)
                await asyncio.sleep(5); continue

            # 4. wait SMS
            await prog.set_slot(slot, f"📬 منتظر SMS → {phone_fmt}")
            code = await get_sms_code(activation_id, timeout=90)
            if not code:
                await prog.set_slot(slot, f"❌ SMS نرسید — بعدی")
                continue

            # 5. sign in
            await prog.set_slot(slot, f"🔑 ورود → {phone_fmt}")
            try:
                await asyncio.wait_for(
                    client.sign_in(phone_fmt, code,
                                   phone_code_hash=sent.phone_code_hash),
                    timeout=20)
            except (PhoneCodeExpiredError, PhoneCodeInvalidError):
                await prog.set_slot(slot, f"❌ کد اشتباه/منقضی — بعدی")
                await cancel_number(activation_id); continue
            except SessionPasswordNeededError:
                await prog.set_slot(slot, f"⚠️ 2FA — بعدی")
                await cancel_number(activation_id); continue
            except FloodWaitError as e:
                await prog.set_slot(slot, f"⏳ FloodWait {e.seconds}s")
                await cancel_number(activation_id)
                await asyncio.sleep(min(e.seconds, 60)); continue
            except Exception as e:
                await prog.set_slot(slot, f"⚠️ {str(e)[:30]}")
                await cancel_number(activation_id)
                await asyncio.sleep(5); continue

            # 6. verify
            if not await client.is_user_authorized():
                await prog.set_slot(slot, f"❌ unauthorized — بعدی")
                await cancel_number(activation_id); continue

            # 7. get me + profile
            me = await asyncio.wait_for(client.get_me(), timeout=10)
            if not me.first_name:
                await _set_random_profile(client)
                me = await client.get_me()

            # 8. confirm + save
            await confirm_number(activation_id)
            await session_store.save_one(sname, {
                "phone":    phone_fmt,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
                "country":  country_id,
                "price":    price,
            })

            name_str = f"@{me.username}" if me.username else (me.first_name or "?")
            logger.info("[slot%d] ✅ %s — %s (#%d)", slot, phone_fmt, name_str, attempt)
            return True, f"✅ {phone_fmt} — {name_str} ({cname})"

        except asyncio.CancelledError:
            if activation_id:
                try: await cancel_number(activation_id)
                except Exception: pass
            raise
        except Exception as e:
            if activation_id:
                try: await cancel_number(activation_id)
                except Exception: pass
            logger.error("[slot%d] unexpected: %s", slot, e, exc_info=True)
            await prog.set_slot(slot, f"⚠️ {str(e)[:30]} — retry")
            await asyncio.sleep(5)
        finally:
            if client:
                try: await client.disconnect()
                except Exception: pass


# ─── buyer task ───────────────────────────────────────────────────────────────────────────────

async def _buyer_task(count: int, status_msg, bot, chat_id: int):
    prog = Progress(count)

    async def worker(slot: int):
        ok, desc = await _buy_one(slot, prog)
        await prog.record(slot, ok, desc)

    async def live_loop():
        """Update message every 3s. Spinner ensures text always changes."""
        while prog.done < prog.total:
            try:
                await status_msg.edit_text(
                    prog.render(), parse_mode="HTML"
                )
            except Exception:
                pass
            await asyncio.sleep(3)

    logger.info("[buyer] launching %d workers", count)
    workers   = [asyncio.create_task(worker(i + 1)) for i in range(count)]
    live_task = asyncio.create_task(live_loop())

    try:
        await asyncio.gather(*workers)
    except asyncio.CancelledError:
        for w in workers:
            w.cancel()
        raise
    finally:
        live_task.cancel()
        try:
            await live_task
        except asyncio.CancelledError:
            pass

    logger.info("[buyer] done. success=%d failed=%d", prog.success, prog.failed)

    final = [
        f"🏁 <b>خرید تموم شد!</b>",
        f"✅ موفق: <b>{prog.success}</b>  "
        f"❌ ناموفق: <b>{prog.failed}</b>  "
        f"⏱ {prog.elapsed()}",
        "",
    ] + prog.results
    try:
        await bot.send_message(
            chat_id, "\n".join(final),
            reply_markup=auto_session_menu(), parse_mode="HTML"
        )
    except Exception as e:
        logger.error("[buyer] final send: %s", e)


# ─── menu ──────────────────────────────────────────────────────────────────────────────────

def auto_session_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 خرید خودکار سشن",      callback_data="autosess_start")],
        [InlineKeyboardButton(text="⏹ لغو خرید",              callback_data="autosess_cancel")],
        [InlineKeyboardButton(text="🧹 پاکسازی سشن‌های نامعتبر", callback_data="autosess_cleanup")],
        [InlineKeyboardButton(text="💰 موجودی HeroSMS",         callback_data="autosess_balance")],
        [InlineKeyboardButton(text="🔙 بازگشت",                 callback_data="menu_main")],
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
        await cb.message.edit_text(
            "\n".join(lines), reply_markup=auto_session_menu(), parse_mode="HTML")
    except HeroSMSError as e:
        await cb.message.edit_text(
            f"❌ {e}", reply_markup=auto_session_menu(), parse_mode="HTML")


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
        await cb.message.edit_text(
            f"❌ {e}", reply_markup=auto_session_menu(), parse_mode="HTML")


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
        f"⏳ شروع خرید <b>{count}</b> سشن — ⚡ <b>{CONCURRENCY}</b> ورکر همزمان...",
        parse_mode="HTML",
    )
    task = asyncio.create_task(
        _buyer_task(count, status_msg, msg.bot, msg.chat.id)
    )
    _active_tasks[msg.from_user.id] = task
