"""
User panel — profile, wallet, deposit, live order tracking, support.
"""
import logging
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
from services.settings_service import get_setting, get_wallets, get_active_coins, get_active_coins, get_active_coins
from services.order_service import get_user_orders, get_order_by_id
from services.smmpass import get_order_status

logger = logging.getLogger("user")
router = Router()

STATUS_ICONS = {
    "pending":    ("⏳", "در صف"),
    "processing": ("🔄", "در حال انجام"),
    "in progress":("🔄", "در حال انجام"),
    "completed":  ("✅", "تکمیل شده"),
    "partial":    ("⚠️", "ناقص"),
    "cancelled":  ("❌", "کنسل شده"),
    "failed":     ("💔", "ناموفق"),
    "refunded":   ("↩️", "برگشت خورده"),
}


class UserState(StatesGroup):
    verify_phone   = State()
    deposit_amount = State()
    deposit_hash   = State()
    deposit_method = State()


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 پنل SMM",        callback_data="menu_smmpass")],
        [InlineKeyboardButton(text="💰 کیف پول",        callback_data="user_wallet"),
         InlineKeyboardButton(text="📦 سفارش‌های من",   callback_data="user_orders")],
        [InlineKeyboardButton(text="👤 پروفایل",        callback_data="user_profile"),
         InlineKeyboardButton(text="📞 پشتیبانی",       callback_data="user_support")],
    ])


# ── /start ────────────────────────────────────────────────────────────────────
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


# ── Profile ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_profile")
async def user_profile(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    u = db_user
    await cb.message.edit_text(
        f"👤 <b>پروفایل من</b>\n\n"
        f"🔵 نام: <b>{u.display_name()}</b>\n"
        f"🔹 یوزرنیم: @{u.username or '—'}\n"
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
async def verify_phone_contact(msg: Message, state: FSMContext):
    phone = msg.contact.phone_number
    async with AsyncSessionLocal() as session:
        await set_phone(session, msg.from_user.id, phone)
        await session.commit()
    await state.clear()
    await msg.answer(
        f"✅ شماره <code>{phone}</code> ثبت شد.",
        reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
    )


# ── Wallet ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_wallet")
async def user_wallet(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    bal = float(db_user.balance or 0) if db_user else 0
    await cb.message.edit_text(
        f"💰 <b>کیف پول</b>\n\n💵 موجودی: <b>${bal:.2f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 واریز موجودی",    callback_data="user_deposit")],
            [InlineKeyboardButton(text="📋 تاریخچه تراکنش",  callback_data="user_transactions")],
            [InlineKeyboardButton(text="🏠 بازگشت",          callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


# ── Deposit ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_deposit")
async def user_deposit_start(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        coins = await get_active_coins(session)
    if not coins:
        await cb.message.edit_text(
            "⚠️ <b>هیچ روش پرداختی فعال نیست.</b>\n\nلطفاً با پشتیبانی تماس بگیرید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")]
            ]),
            parse_mode="HTML"
        ); return
    btns = [[InlineKeyboardButton(
        text=f"{c['icon']} {c['label']}",
        callback_data=f"dep_coin_{c['key']}"
    )] for c in coins]
    btns.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")])
    await cb.message.edit_text(
        "💳 <b>واریز موجودی</b>\n\n"
        "ارز مورد نظر را انتخاب کنید:\n\n"
        "<i>💡 مبلغ به دلار وارد می‌شود — معادل ارز به‌صورت لحظه‌ای محاسبه می‌شود.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=btns),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("dep_coin_"))
async def user_deposit_coin(cb: CallbackQuery, state: FSMContext):
    coin_key = cb.data.replace("dep_coin_", "")
    await cb.answer()
    async with AsyncSessionLocal() as session:
        coins = await get_active_coins(session)
    coin = next((c for c in coins if c["key"] == coin_key), None)
    if not coin:
        await cb.answer("❌ این ارز دیگر فعال نیست.", show_alert=True); return
    await state.update_data(deposit_coin=coin)
    await state.set_state(UserState.deposit_amount)
    await cb.message.edit_text(
        f"{coin['icon']} <b>واریز {coin['label']}</b>\n\n"
        f"💵 مبلغ مورد نظر را به <b>دلار</b> وارد کنید:\n"
        f"<i>(مثال: 10 یا 25.5)</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="dep_cancel")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "dep_cancel")
async def dep_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "❌ واریز لغو شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 واریز مجدد", callback_data="user_deposit")],
            [InlineKeyboardButton(text="🏠 بازگشت",     callback_data="user_wallet")],
        ])
    )


@router.message(UserState.deposit_amount)
async def user_deposit_amount(msg: Message, state: FSMContext):
    try:
        amount = float((msg.text or "").strip().replace(",", ""))
        if amount <= 0: raise ValueError
    except ValueError:
        await msg.answer(
            "❌ مبلغ معتبر وارد کنید (مثال: 10 یا 25.5)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
            ])
        ); return

    data     = await state.get_data()
    coin     = data.get("deposit_coin", {})
    coin_key = coin.get("key", "usdt_trc")

    from services.price_service import usd_to_coin, format_amount, get_price_usd
    price_usd   = await get_price_usd(coin_key)
    coin_amount = await usd_to_coin(amount, coin_key)
    if coin_amount is None:
        await msg.answer(
            "⚠️ خطا در دریافت قیمت. لطفاً دوباره امتحان کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
            ])
        ); return

    coin_str  = format_amount(coin_amount, coin_key)
    price_str = f"${price_usd:,.4f}" if price_usd and price_usd < 100 else (f"${price_usd:,.2f}" if price_usd else "—")
    addr      = coin.get("address", "—")
    label     = coin.get("label", "")
    icon      = coin.get("icon", "💳")
    network   = coin.get("network", "")
    sym       = label.split()[0] if label else ""

    await state.update_data(deposit_amount=amount, deposit_coin_amount=coin_str)
    await state.set_state(UserState.deposit_hash)

    await msg.answer(
        f"{icon} <b>واریز {label}</b>\n"
        f"{'─'*30}\n"
        f"💵 مبلغ: <b>${amount:,.2f}</b>\n"
        f"📊 قیمت لحظه‌ای: <b>{price_str}</b>\n"
        f"💰 باید ارسال کنید: <b>{coin_str} {sym}</b>\n"
        f"🌐 شبکه: <b>{network}</b>\n"
        f"{'─'*30}\n\n"
        f"📤 <b>آدرس کیف پول:</b>\n"
        f"<code>{addr}</code>\n\n"
        f"<i>👆 روی آدرس بالا ضربه بزنید تا کپی شود</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"📋 کپی مبلغ: {coin_str} {sym}", copy_text=coin_str)],
            [InlineKeyboardButton(text="📋 کپی آدرس کیف پول",            copy_text=addr)],
            [InlineKeyboardButton(text="❌ لغو واریز",                    callback_data="dep_cancel")],
        ]),
        parse_mode="HTML"
    )
    await msg.answer(
        "✅ پس از واریز، <b>هش تراکنش (TX Hash)</b> را ارسال کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
        ]),
        parse_mode="HTML"
    )


@router.message(UserState.deposit_hash)
async def user_deposit_hash(msg: Message, state: FSMContext, db_user: User = None):
    data     = await state.get_data()
    amount   = data.get("deposit_amount", 0)
    coin     = data.get("deposit_coin", {})
    coin_str = data.get("deposit_coin_amount", "")
    method   = coin.get("label", "USDT")
    addr     = coin.get("address", "")
    tx_hash  = (msg.text or "").strip()
    if not tx_hash:
        await msg.answer("❌ هش تراکنش نمی‌تواند خالی باشد."); return
    user_id = db_user.id if db_user else msg.from_user.id
    async with AsyncSessionLocal() as session:
        await create_deposit_request(session, user_id, amount, method, tx_hash, addr)
        await session.commit()
    await state.clear()
    sym = method.split()[0] if method else ""
    await msg.answer(
        f"✅ <b>درخواست واریز ثبت شد!</b>\n"
        f"{'─'*30}\n"
        f"💵 مبلغ: <b>${amount:,.2f}</b>\n"
        f"💰 ارسالی: <b>{coin_str} {sym}</b>\n"
        f"🔗 هش: <code>{tx_hash[:40]}{'...' if len(tx_hash)>40 else ''}</code>\n"
        f"{'─'*30}\n\n"
        f"⏳ پس از تایید ادمین، موجودی شما شارژ می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="user_home")]
        ]),
        parse_mode="HTML"
    )




# ── Transactions ──────────────────────────────────────────────────────────────
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
    TYPE_FA = {"deposit":"واریز","order":"سفارش","refund":"برگشت","manual":"دستی"}
    ST_ICON = {"approved":"✅","pending":"⏳","rejected":"❌"}
    rows = []
    for tx in txs[:15]:
        icon = ST_ICON.get(tx.status, "🟡")
        tp   = TYPE_FA.get(tx.type, tx.type)
        rows.append(
            f"{icon} <b>${float(tx.amount):.2f}</b> | {tp} | {tx.method or '—'}\n"
            f"   📅 {tx.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    await cb.message.edit_text(
        "📋 <b>تراکنش‌های من</b>\n\n" + "\n\n".join(rows),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_wallet")]
        ]),
        parse_mode="HTML"
    )


# ── Orders — live tracking ────────────────────────────────────────────────────
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
    buttons = []
    for o in orders[:12]:
        icon, label = STATUS_ICONS.get(o.status, ("🟡", o.status))
        buttons.append([InlineKeyboardButton(
            text=f"{icon} #{o.id} | {o.service_name[:22]} | {label}",
            callback_data=f"user_order_{o.id}"
        )])
    buttons.append([
        InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="menu_smmpass"),
        InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_home"),
    ])
    await cb.message.edit_text(
        "📦 <b>سفارش‌های من</b>\n\nبرای جزئیات و وضعیت لحظه‌ای روی سفارش کلیک کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("user_order_"))
async def user_order_detail(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    order_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)
    if not order or order.user_id != db_user.id:
        await cb.answer("سفارش یافت نشد!", show_alert=True); return

    # وضعیت لحظه‌ای از API
    live_status = order.status
    live_start  = order.start_count
    live_remains = order.remains
    api_error   = None
    try:
        api_data    = await get_order_status(order.service_id)
        live_status = api_data.get("status", order.status).lower()
        live_start  = api_data.get("start_count", order.start_count)
        live_remains = api_data.get("remains", order.remains)
        # آپدیت DB
        async with AsyncSessionLocal() as session:
            from services.order_service import update_order_status, process_refund
            updated = await update_order_status(
                session, order_id, live_status,
                start_count=int(live_start) if live_start is not None else None,
                remains=int(live_remains) if live_remains is not None else None,
            )
            # برگشت خودکار پول اگه کنسل یا partial شد
            refunded = 0.0
            if updated and live_status in ("cancelled", "partial") and order.status != live_status:
                refunded = await process_refund(session, updated)
            await session.commit()
    except Exception as e:
        api_error = str(e)[:80]

    icon, label = STATUS_ICONS.get(live_status, ("🟡", live_status))
    done = 0
    if live_start is not None and live_remains is not None:
        try:
            done = int(live_start) - int(live_remains)
        except Exception:
            done = 0

    text = (
        f"📦 <b>سفارش #{order.id}</b>\n\n"
        f"🛒 سرویس: <b>{order.service_name}</b>\n"
        f"🔗 لینک: <code>{order.link}</code>\n"
        f"🔢 تعداد: <b>{order.quantity:,}</b>\n"
        f"💰 پرداخت: <b>${float(order.sell_price):.4f}</b>\n"
        f"📅 تاریخ: <b>{order.created_at.strftime('%Y-%m-%d %H:%M')}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{icon} وضعیت: <b>{label}</b>\n"
    )
    if live_start is not None:
        text += f"🔢 شروع از: <b>{live_start:,}</b>\n"
    if live_remains is not None:
        text += f"⏳ باقی‌مانده: <b>{int(live_remains):,}</b>\n"
    if done > 0:
        text += f"✅ انجام شده: <b>{done:,}</b>\n"
    if api_error:
        text += f"\n⚠️ <i>خطا در دریافت وضعیت: {api_error}</i>\n"
    if live_status == "cancelled":
        text += f"\n↩️ <b>موجودی برگشت خورد!</b>"
    elif live_status == "partial":
        text += f"\n↩️ <b>مابقی برگشت خورد!</b>"

    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"user_order_{order_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت",    callback_data="user_orders")],
        ]),
        parse_mode="HTML"
    )


# ── Support ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "user_support")
async def user_support(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        support_url = await get_setting(session, "support_url", "")
    buttons = []
    if support_url and support_url.startswith("http"):
        buttons.append([InlineKeyboardButton(text="💬 ارتباط با پشتیبانی", url=support_url)])
    elif support_url and support_url.startswith("@"):
        buttons.append([InlineKeyboardButton(
            text="💬 ارتباط با پشتیبانی",
            url=f"https://t.me/{support_url.lstrip('@')}"
        )])
    buttons.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])
    text = (
        "📞 <b>پشتیبانی</b>\n\n"
        "برای ارتباط با تیم پشتیبانی کلیک کنید 👇"
        if support_url else
        "📞 <b>پشتیبانی</b>\n\n⚠️ در حال حاضر پشتیبانی آنلاین در دسترس نیست."
    )
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )
