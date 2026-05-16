"""
User panel handler - profile, balance, deposit, orders, SMM.
"""
import os
import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User
from services.user_service import get_user, set_phone, create_verification_code, verify_code
from services.deposit_service import (
    create_deposit_request, get_user_transactions
)
from services.settings_service import get_setting, get_wallets
from services.order_service import get_user_orders

logger   = logging.getLogger("user")
router   = Router()


class UserState(StatesGroup):
    verify_phone    = State()
    deposit_amount  = State()
    deposit_hash    = State()
    deposit_method  = State()


# ─── Main menu keyboard ────────────────────────────────────────────────────────────────
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 پنل SMM",          callback_data="user_smm")],
        [InlineKeyboardButton(text="💰 کیف پول",          callback_data="user_wallet")],
        [InlineKeyboardButton(text="📦 سفارش‌های من",       callback_data="user_orders")],
        [InlineKeyboardButton(text="👤 پروفایل من",         callback_data="user_profile")],
        [InlineKeyboardButton(text="🔗 لینک دعوت",          callback_data="user_referral")],
        [InlineKeyboardButton(text="📞 پشتیبانی",           callback_data="user_support")],
    ])


# ─── /start ────────────────────────────────────────────────────────────────────────────────
@router.message(F.text.startswith("/start"))
async def cmd_start(msg: Message, state: FSMContext, db_user: User = None, is_new_user: bool = False):
    await state.clear()
    async with AsyncSessionLocal() as session:
        bot_name = await get_setting(session, "bot_name", "SMM Panel")
        welcome  = await get_setting(session, "welcome_message", "خوش آمدید! 👋")

    name = db_user.display_name() if db_user else msg.from_user.first_name or "User"
    bal  = float(db_user.balance or 0) if db_user else 0

    text = (
        f"🚀 <b>{bot_name}</b>\n\n"
        f"👋 {welcome}\n"
        f"👤 <b>{name}</b>\n"
        f"💰 موجودی: <b>${bal:.2f}</b>\n\n"
        f"یک بخش را انتخاب کنید:"
    )
    await msg.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "user_home")
async def user_home(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await state.clear()
    await cb.answer()
    async with AsyncSessionLocal() as session:
        bot_name = await get_setting(session, "bot_name", "SMM Panel")
    name = db_user.display_name() if db_user else "User"
    bal  = float(db_user.balance or 0) if db_user else 0
    await cb.message.edit_text(
        f"🚀 <b>{bot_name}</b>\n"
        f"👤 <b>{name}</b> | 💰 <b>${bal:.2f}</b>\n\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=main_menu_kb(), parse_mode="HTML"
    )


# ─── Profile ───────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_profile")
async def user_profile(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    u = db_user
    phone = u.phone or "❓ وریفای نشده"
    text = (
        f"👤 <b>پروفایل من</b>\n\n"
        f"🔵 نام: <b>{u.display_name()}</b>\n"
        f"🔹 یوزرنیم: @{u.username or '-'}\n"
        f"📱 شماره: <b>{phone}</b>\n"
        f"💰 موجودی: <b>${float(u.balance or 0):.2f}</b>\n"
        f"👥 دعوت: <b>{u.referral_count}</b> نفر\n"
        f"📅 عضویت: <b>{u.created_at.strftime('%Y-%m-%d')}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 وریفای شماره", callback_data="user_verify_phone")],
        [InlineKeyboardButton(text="🏠 بازگشت",            callback_data="user_home")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ─── Phone verification ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_verify_phone")
async def verify_phone_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(UserState.verify_phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 ارسال شماره", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await cb.message.answer(
        "📱 <b>وریفای شماره</b>\n\n"
        "دکمه زیر را بزنید تا شمارهتان به بات ارسال شود:",
        reply_markup=kb, parse_mode="HTML"
    )


@router.message(UserState.verify_phone, F.contact)
async def verify_phone_contact(msg: Message, state: FSMContext, db_user: User = None):
    phone = msg.contact.phone_number
    async with AsyncSessionLocal() as session:
        await set_phone(session, msg.from_user.id, phone)
    await state.clear()
    await msg.answer(
        f"✅ شماره <b>{phone}</b> وریفای شد!",
        reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
    )
    await msg.answer("🏠 منو اصلی:", reply_markup=main_menu_kb())


# ─── Wallet ───────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_wallet")
async def user_wallet(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    bal = float(db_user.balance or 0) if db_user else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ شارژ حساب",     callback_data="user_deposit")],
        [InlineKeyboardButton(text="📜 تاریخچه تراکنش‌ها", callback_data="user_txlist_0")],
        [InlineKeyboardButton(text="🏠 بازگشت",          callback_data="user_home")],
    ])
    await cb.message.edit_text(
        f"💰 <b>کیف پول</b>\n\n"
        f"💵 موجودی: <b>${bal:.2f}</b>",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data == "user_deposit")
async def user_deposit_menu(cb: CallbackQuery):
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 USDT (TRC20)", callback_data="dep_usdt")],
        [InlineKeyboardButton(text="💎 TON",          callback_data="dep_ton")],
        [InlineKeyboardButton(text="⚡ TRX",          callback_data="dep_trx")],
        [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_wallet")],
    ])
    await cb.message.edit_text(
        "➕ <b>شارژ حساب</b>\n\n"
        "روش پرداخت را انتخاب کنید:",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"dep_usdt", "dep_ton", "dep_trx"}))
async def deposit_method(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    method_map = {"dep_usdt": "usdt", "dep_ton": "ton", "dep_trx": "trx"}
    method = method_map[cb.data]
    await state.update_data(dep_method=method)

    async with AsyncSessionLocal() as session:
        wallets = await get_wallets(session)
        min_dep = await get_setting(session, "min_deposit", "1")
        max_dep = await get_setting(session, "max_deposit", "1000")

    wallet_key = f"{method}_wallet"
    wallet_addr = wallets.get(wallet_key, "")
    if not wallet_addr:
        await cb.message.edit_text(
            "❌ آدرس کیف پول تنظیم نشده. با پشتیبانی تماس بگیرید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_deposit")]
            ])
        )
        return

    method_label = {"usdt": "USDT (TRC20)", "ton": "TON", "trx": "TRX"}.get(method, method)
    await state.set_state(UserState.deposit_amount)
    await cb.message.edit_text(
        f"🟢 <b>شارژ با {method_label}</b>\n\n"
        f"💳 آدرس کیف پول:\n<code>{wallet_addr}</code>\n\n"
        f"📌 حداقل: <b>${min_dep}</b> | حداکثر: <b>${max_dep}</b>\n\n"
        "❗️ مبلغ واریزی را به دلار وارد کنید:",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_amount)
async def deposit_amount(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ مبلغ معتبر وارد کنید."); return

    async with AsyncSessionLocal() as session:
        min_dep = float(await get_setting(session, "min_deposit", "1"))
        max_dep = float(await get_setting(session, "max_deposit", "1000"))

    if amount < min_dep or amount > max_dep:
        await msg.answer(f"❌ مبلغ باید بین <b>${min_dep}</b> و <b>${max_dep}</b> باشد.", parse_mode="HTML"); return

    await state.update_data(dep_amount=amount)
    await state.set_state(UserState.deposit_hash)
    await msg.answer(
        f"✅ مبلغ: <b>${amount}</b>\n\n"
        "🔗 اکنون هش تراکنش (TX Hash) را وارد کنید:",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_hash)
async def deposit_hash(msg: Message, state: FSMContext, db_user: User = None):
    tx_hash = msg.text.strip()
    data    = await state.get_data()
    amount  = data.get("dep_amount", 0)
    method  = data.get("dep_method", "usdt")
    await state.clear()

    async with AsyncSessionLocal() as session:
        from services.user_service import get_user
        user = await get_user(session, msg.from_user.id)
        if not user:
            await msg.answer("❌ خطای داخلی."); return
        tx = await create_deposit_request(
            session, user.id, amount, method, tx_hash
        )
        tx_id = tx.id

    # Notify admin
    admin_id = int(os.getenv("ADMIN_ID", "0"))
    try:
        from aiogram import Bot
        bot = Bot.get_current()
        if bot and admin_id:
            await bot.send_message(
                admin_id,
                f"💰 <b>درخواست واریز جدید</b>\n\n"
                f"👤 کاربر: @{msg.from_user.username or msg.from_user.id}\n"
                f"💵 مبلغ: <b>${amount}</b>\n"
                f"💳 روش: <b>{method.upper()}</b>\n"
                f"🔗 Hash: <code>{tx_hash}</code>\n"
                f"🔢 ID: <code>{tx_id}</code>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ تایید", callback_data=f"adm_dep_ok_{tx_id}"),
                     InlineKeyboardButton(text="❌ رد",    callback_data=f"adm_dep_no_{tx_id}")],
                ]),
                parse_mode="HTML"
            )
    except Exception:
        pass

    await msg.answer(
        f"✅ <b>درخواست واریز ثبت شد!</b>\n\n"
        f"🔢 شناسه: <code>{tx_id}</code>\n"
        "⏳ در حال بررسی توسط ادمین...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 منو اصلی", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )


# ─── Transaction history ───────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("user_txlist_"))
async def user_txlist(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        user = await get_user(session, cb.from_user.id)
        txs  = await get_user_transactions(session, user.id, page=page)

    if not txs:
        await cb.message.edit_text(
            "📜 تاریخچه تراکنش‌ها خالی است.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")]
            ])
        )
        return

    type_icon = {"deposit": "⬆️", "order": "📦", "refund": "↩️", "manual": "🔧"}
    status_icon = {"approved": "✅", "pending": "⏳", "rejected": "❌"}
    lines = []
    for tx in txs:
        ti = type_icon.get(tx.type, "🔹")
        si = status_icon.get(tx.status, "🔵")
        sign = "+" if tx.amount > 0 else ""
        lines.append(f"{ti} {si} <b>{sign}${float(tx.amount):.2f}</b> — {tx.created_at.strftime('%m/%d %H:%M')}")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"user_txlist_{page-1}"))
    if len(txs) == 10:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"user_txlist_{page+1}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")])

    await cb.message.edit_text(
        "📜 <b>تاریخچه تراکنش‌ها</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


# ─── Orders ───────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("user_orders"))
async def user_orders(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    page = 0
    if "_" in cb.data[11:]:
        try: page = int(cb.data.split("_")[-1])
        except: pass

    async with AsyncSessionLocal() as session:
        user   = await get_user(session, cb.from_user.id)
        orders = await get_user_orders(session, user.id, page=page)

    if not orders:
        await cb.message.edit_text(
            "📦 هنوز سفارشی ثبت نکرده‌اید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 پنل SMM", callback_data="user_smm")],
                [InlineKeyboardButton(text="🏠 بازگشت",   callback_data="user_home")],
            ])
        )
        return

    status_icon = {"pending": "⏳", "processing": "⏳", "completed": "✅", "cancelled": "❌", "partial": "⚠️"}
    lines = []
    for o in orders:
        si = status_icon.get(o.status, "🔵")
        lines.append(
            f"{si} <b>#{o.id}</b> [{o.service_id}] {o.service_name[:20]}\n"
            f"   💰 ${float(o.sell_price):.2f} | 📅 {o.created_at.strftime('%m/%d')}"
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"user_orders_{page-1}"))
    if len(orders) == 10:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"user_orders_{page+1}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])

    await cb.message.edit_text(
        "📦 <b>سفارش‌های من</b>\n\n" + "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


# ─── Referral ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_referral")
async def user_referral(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    bot_username = (await cb.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{db_user.referral_code}"
    await cb.message.edit_text(
        f"🔗 <b>لینک دعوت</b>\n\n"
        f"👥 دعوت شده: <b>{db_user.referral_count}</b> نفر\n\n"
        f"🔗 لینک شما:\n<code>{ref_link}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )


# ─── Support ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_support")
async def user_support(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        support = await get_setting(session, "support_username", "")
    text = (
        "📞 <b>پشتیبانی</b>\n\n"
        f"👤 برای ارتباط با پشتیبانی:\n"
        f"@{support}" if support else "❌ پشتیبانی تنظیم نشده."
    )
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )


# ─── SMM redirect ─────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_smm")
async def user_smm(cb: CallbackQuery, state: FSMContext):
    """Redirect to SMM panel (user version)."""
    await state.clear()
    await cb.answer()
    # Will be handled by user_smmpass_handler
    from handlers.user_smmpass_handler import show_user_smm_menu
    await show_user_smm_menu(cb)
