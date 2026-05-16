"""
User panel — profile, wallet, deposit, orders, support.
"""
import logging, os
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User
from services.user_service import get_user, set_phone
from services.deposit_service import create_deposit_request, get_user_transactions
from services.settings_service import get_setting, get_wallets
from services.order_service import get_user_orders

logger = logging.getLogger("user")
router = Router()


class UserState(StatesGroup):
    verify_phone   = State()
    deposit_amount = State()
    deposit_hash   = State()
    deposit_method = State()


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 پنل SMM",       callback_data="menu_smmpass")],
        [InlineKeyboardButton(text="💰 کیف پول",       callback_data="user_wallet"),
         InlineKeyboardButton(text="📦 سفارش‌های من",  callback_data="user_orders")],
        [InlineKeyboardButton(text="👤 پروفایل",       callback_data="user_profile"),
         InlineKeyboardButton(text="📞 پشتیبانی",      callback_data="user_support")],
    ])


@router.message(F.text.startswith("/start"))
async def cmd_start(msg: Message, state: FSMContext,
                    db_user: User = None, is_new_user: bool = False,
                    is_admin: bool = False, is_superadmin: bool = False):
    await state.clear()
    async with AsyncSessionLocal() as session:
        bot_name = await get_setting(session, "bot_name", "SMM Panel")
        welcome  = await get_setting(session, "welcome_message", "خوش آمدید! 👋")
    name = db_user.display_name() if db_user else (msg.from_user.first_name or "User")
    bal  = float(db_user.balance or 0) if db_user else 0
    if is_superadmin or is_admin:
        await msg.answer(
            f"👋 <b>{name}</b> | 🔑 ادمین\n💰 موجودی: <b>${bal:.2f}</b>\n\nیک بخش را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔧 پنل مدیریت", callback_data="menu_admin")],
                [InlineKeyboardButton(text="👤 پنل کاربری",  callback_data="user_home")],
            ]),
            parse_mode="HTML"
        )
        return
    await msg.answer(
        f"🚀 <b>{bot_name}</b>\n\n"
        f"👋 {welcome}\n"
        f"👤 <b>{name}</b>\n"
        f"💰 موجودی: <b>${bal:.2f}</b>\n\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )


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
        reply_markup=main_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_profile")
async def user_profile(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    u = db_user
    await cb.message.edit_text(
        f"👤 <b>پروفایل من</b>\n\n"
        f"🔵 نام: <b>{u.display_name()}</b>\n"
        f"🔹 یوزرنیم: @{u.username or '-'}\n"
        f"📱 شماره: <b>{u.phone or '— تایید نشده'}</b>\n"
        f"💰 موجودی: <b>${float(u.balance or 0):.2f}</b>\n"
        f"👥 دعوت‌ها: <b>{u.referral_count}</b> نفر\n"
        f"📅 عضویت: <b>{u.created_at.strftime('%Y-%m-%d')}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 تایید شماره", callback_data="user_verify_phone")],
            [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_verify_phone")
async def verify_phone_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(UserState.verify_phone)
    await cb.message.answer(
        "📱 لطفاً شماره خود را ارسال کنید:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 ارسال شماره", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )


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
    await cb.message.edit_text(
        f"💰 <b>کیف پول</b>\n\n💵 موجودی: <b>${bal:.2f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 واریز موجودی",   callback_data="user_deposit")],
            [InlineKeyboardButton(text="📋 تاریخچه تراکنش", callback_data="user_transactions")],
            [InlineKeyboardButton(text="🏠 بازگشت",         callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_deposit")
async def user_deposit_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_text(
        "💳 <b>واریز موجودی</b>\n\nروش پرداخت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🟢 USDT (TRC20)", callback_data="dep_usdt")],
            [InlineKeyboardButton(text="💎 TON",           callback_data="dep_ton")],
            [InlineKeyboardButton(text="⚡ TRX",           callback_data="dep_trx")],
            [InlineKeyboardButton(text="🏠 بازگشت",        callback_data="user_wallet")],
        ]),
        parse_mode="HTML"
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
        f"مبلغ مورد نظر را به دلار وارد کنید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_amount)
async def user_deposit_amount(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        amount = float(msg.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ مبلغ معتبر وارد کنید."); return
    await state.update_data(deposit_amount=amount)
    await state.set_state(UserState.deposit_hash)
    await msg.answer(
        f"✅ مبلغ: <b>${amount:.2f}</b>\n\n📝 هش تراکنش را وارد کنید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_hash)
async def user_deposit_hash(msg: Message, state: FSMContext, db_user: User = None):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    data    = await state.get_data()
    amount  = data.get("deposit_amount", 0)
    method  = data.get("deposit_method", "USDT")
    tx_hash = (msg.text or "").strip()
    async with AsyncSessionLocal() as session:
        await create_deposit_request(session, db_user.id, amount, method, tx_hash)
        await session.commit()
    await state.clear()
    await msg.answer(
        f"✅ <b>درخواست واریز ثبت شد.</b>\n"
        f"💵 مبلغ: <b>${amount:.2f}</b> | روش: <b>{method}</b>\n"
        "⏳ در حال بررسی توسط ادمین...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_transactions")
async def user_transactions(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        txs = await get_user_transactions(session, db_user.id)
    if not txs:
        await cb.message.edit_text(
            "📋 تاریخچه تراکنش خالی است.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")]
            ])
        ); return
    rows = []
    for tx in txs[:10]:
        icon = "✅" if tx.status == "approved" else ("❌" if tx.status == "rejected" else "⏳")
        rows.append(f"{icon} <b>${float(tx.amount):.2f}</b> | {tx.method} | {tx.created_at.strftime('%m/%d %H:%M')}")
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
                [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="menu_smmpass")],
                [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_home")],
            ])
        ); return
    ST = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","cancelled":"❌","failed":"💔"}
    lines = []
    for o in orders[:10]:
        icon = ST.get(o.status, "🟡")
        lines.append(
            f"{icon} <b>#{o.id}</b> {o.service_name[:25]}\n"
            f"   🔢{o.quantity:,} 💰${float(o.sell_price):.4f} 📅{o.created_at.strftime('%m/%d')}"
        )
    await cb.message.edit_text(
        "📦 <b>سفارش‌های من</b>\n\n" + "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="menu_smmpass")],
            [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "user_support")
async def user_support(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        support_url = await get_setting(session, "support_url", "")
    text = "📞 <b>پشتیبانی</b>\n\n"
    buttons = []
    if support_url:
        text += f"برای ارتباط با پشتیبانی کلیک کنید:"
        buttons.append([InlineKeyboardButton(text="💬 پشتیبانی", url=support_url)])
    else:
        text += "در حال حاضر پشتیبانی آنلاین در دسترس نیست."
    buttons.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
