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


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 پنل SMM",          callback_data="user_smm")],
        [InlineKeyboardButton(text="💰 کیف پول",          callback_data="user_wallet")],
        [InlineKeyboardButton(text="📦 سفارش‌های من",       callback_data="user_orders")],
        [InlineKeyboardButton(text="👤 پروفایل من",         callback_data="user_profile")],
        [InlineKeyboardButton(text="🔗 لینک دعوت",          callback_data="user_referral")],
        [InlineKeyboardButton(text="📞 پشتیبانی",           callback_data="user_support")],
    ])


@router.message(F.text.startswith("/start"))
async def cmd_start(msg: Message, state: FSMContext, db_user: User = None, is_new_user: bool = False, is_admin: bool = False, is_superadmin: bool = False):
    await state.clear()
    async with AsyncSessionLocal() as session:
        bot_name = await get_setting(session, "bot_name", "SMM Panel")
        welcome  = await get_setting(session, "welcome_message", "خوش آمدید! 👋")

    name = db_user.display_name() if db_user else msg.from_user.first_name or "User"
    bal  = float(db_user.balance or 0) if db_user else 0

    if is_superadmin or is_admin:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔧 پنل مدیریت", callback_data="menu_admin")],
            [InlineKeyboardButton(text="👤 پنل کاربری",  callback_data="user_home")],
        ])
        await msg.answer(
            f"👋 <b>{name}</b> | 🔑 ادمین\n"
            f"💰 موجودی: <b>${bal:.2f}</b>\n\n"
            "یک بخش را انتخاب کنید:",
            reply_markup=admin_kb, parse_mode="HTML"
        )
        return

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


@router.callback_query(F.data == "user_profile")
async def user_profile(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    u = db_user
    phone = u.phone or "— تایید نشده"
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
        [InlineKeyboardButton(text="📱 تایید شماره", callback_data="user_verify_phone")],
        [InlineKeyboardButton(text="🏠 بازگشت",            callback_data="user_home")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "user_verify_phone")
async def verify_phone_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(UserState.verify_phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 ارسال شماره", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await cb.message.answer("📱 لطفاً شماره خود را ارسال کنید:", reply_markup=kb)


@router.message(UserState.verify_phone, F.contact)
async def verify_phone_contact(msg: Message, state: FSMContext, db_user: User = None):
    phone = msg.contact.phone_number
    async with AsyncSessionLocal() as session:
        await set_phone(session, msg.from_user.id, phone)
    await state.clear()
    await msg.answer(
        f"✅ شماره <code>{phone}</code> ثبت شد.",
        reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
    )


@router.callback_query(F.data == "user_wallet")
async def user_wallet(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    bal = float(db_user.balance or 0) if db_user else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 واریز موجودی", callback_data="user_deposit")],
        [InlineKeyboardButton(text="📋 تاریخچه تراکنش", callback_data="user_transactions")],
        [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")],
    ])
    await cb.message.edit_text(
        f"💰 <b>کیف پول</b>\n\n💵 موجودی: <b>${bal:.2f}</b>",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data == "user_deposit")
async def user_deposit_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 USDT (TRC20)", callback_data="dep_usdt")],
        [InlineKeyboardButton(text="💎 TON",          callback_data="dep_ton")],
        [InlineKeyboardButton(text="⚡ TRX",               callback_data="dep_trx")],
        [InlineKeyboardButton(text="🏠 بازگشت",        callback_data="user_wallet")],
    ])
    await cb.message.edit_text(
        "💳 <b>واریز موجودی</b>\n\nروش پرداخت را انتخاب کنید:",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"dep_usdt", "dep_ton", "dep_trx"}))
async def user_deposit_method(cb: CallbackQuery, state: FSMContext):
    method_map = {"dep_usdt": "USDT", "dep_ton": "TON", "dep_trx": "TRX"}
    method = method_map[cb.data]
    await state.update_data(deposit_method=method)
    await state.set_state(UserState.deposit_amount)
    await cb.answer()
    async with AsyncSessionLocal() as session:
        wallets = await get_wallets(session)
    wallet_addr = wallets.get(method.lower(), "—")
    await cb.message.edit_text(
        f"💳 <b>واریز {method}</b>\n\n"
        f"📤 آدرس کیف پول:\n<code>{wallet_addr}</code>\n\n"
        f"مبلغ مورد نظر را به دلار وارد کنید:",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_amount)
async def user_deposit_amount(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ مبلغ معتبر وارد کنید.")
        return
    await state.update_data(deposit_amount=amount)
    await state.set_state(UserState.deposit_hash)
    await msg.answer(f"✅ مبلغ: <b>${amount:.2f}</b>\n\n📝 هش تراکنش را وارد کنید:", parse_mode="HTML")


@router.message(UserState.deposit_hash)
async def user_deposit_hash(msg: Message, state: FSMContext, db_user: User = None):
    data = await state.get_data()
    amount = data.get("deposit_amount", 0)
    method = data.get("deposit_method", "USDT")
    tx_hash = msg.text.strip()
    async with AsyncSessionLocal() as session:
        await create_deposit_request(session, db_user.id, amount, method, tx_hash)
    await state.clear()
    await msg.answer(
        f"✅ <b>درخواست واریز ثبت شد.</b>\n"
        f"💵 مبلغ: ${amount:.2f} | روش: {method}\n"
        "⏳ در حال بررسی توسط ادمین...",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_transactions")
async def user_transactions(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        txs = await get_user_transactions(session, db_user.id)
    if not txs:
        await cb.message.edit_text(
            "📋 تاریخچهای تراکنشی خالی است.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")]
            ])
        )
        return
    rows = []
    for tx in txs[:10]:
        icon = "✅" if tx.status == "approved" else ("❌" if tx.status == "rejected" else "⏳")
        rows.append(f"{icon} ${float(tx.amount):.2f} | {tx.method} | {tx.created_at.strftime('%m/%d')}")
    await cb.message.edit_text(
        "📋 <b>تراکنش‌ها</b>\n\n" + "\n".join(rows),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_orders")
async def user_orders(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, db_user.id)
    if not orders:
        await cb.message.edit_text(
            "📦 هیچ سفارشی وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
            ])
        )
        return
    rows = []
    for o in orders[:10]:
        rows.append(f"📦 #{o.id} | {o.service_name[:20]} | {o.status} | ${float(o.sell_price):.2f}")
    await cb.message.edit_text(
        "📦 <b>سفارش‌های من</b>\n\n" + "\n".join(rows),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_referral")
async def user_referral(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    bot_info = await cb.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{db_user.telegram_id}"
    await cb.message.edit_text(
        f"🔗 <b>لینک دعوت</b>\n\n"
        f"👥 دعوت شده: <b>{db_user.referral_count}</b> نفر\n\n"
        f"🔗 لینک شما:\n<code>{ref_link}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_support")
async def user_support(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        support_username = await get_setting(session, "support_username", "")
    text = "📞 <b>پشتیبانی</b>\n\n"
    if support_username:
        text += f"💬 برای ارتباط: @{support_username}"
    else:
        text += "پشتیبانی در دسترس نیست."
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )
