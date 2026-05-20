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
from services.settings_service import get_setting, get_wallets, get_active_coins
from services.order_service import get_user_orders, get_order_by_id
from services.price_service import get_price_usd, usd_to_coin, format_amount
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


async def main_menu_kb(smm_title: str = "🛒 پنل SMM") -> InlineKeyboardMarkup:
    """منوی داینامیک — SMMPass + پنل‌های دستی از DB"""
    rows = []
    rows.append([InlineKeyboardButton(text=smm_title, callback_data="menu_smmpass")])
    try:
        from services.panel_service import get_all_panels
        async with AsyncSessionLocal() as _ps:
            panels = await get_all_panels(_ps, active_only=True)
        for p in panels:
            rows.append([InlineKeyboardButton(
                text=p.button_label,
                callback_data=f"panel_user_{p.id}"
            )])
    except Exception:
        pass
    rows.append([
        InlineKeyboardButton(text="💰 کیف پول",      callback_data="user_wallet"),
        InlineKeyboardButton(text="📦 سفارش‌های من", callback_data="user_orders"),
    ])
    rows.append([
        InlineKeyboardButton(text="👤 پروفایل",      callback_data="user_profile"),
        InlineKeyboardButton(text="📞 پشتیبانی",     callback_data="user_support"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    async with AsyncSessionLocal() as _s:
        smm_title = await get_setting(_s, "smm_panel_title", "🛒 پنل SMM")
    await msg.answer(
        f"🚀 <b>{bot_name}</b>\n\n"
        f"👋 {welcome}\n"
        f"👤 <b>{name}</b>\n"
        f"💰 موجودی: <b>${bal:.2f}</b>\n\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=await main_menu_kb(smm_title),
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
    async with AsyncSessionLocal() as _s:
        smm_title = await get_setting(_s, "smm_panel_title", "🛒 پنل SMM")
    await cb.message.edit_text(
        f"🚀 <b>{bot_name}</b>\n"
        f"👤 <b>{name}</b> | 💰 <b>${bal:.2f}</b>\n\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=await main_menu_kb(smm_title),
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

    try:
        data     = await state.get_data()
        coin     = data.get("deposit_coin", {})
        coin_key = coin.get("key", "usdt_trc")

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

        await state.update_data(deposit_amount=amount, deposit_coin_amount=coin_str, deposit_hash_tries=0)
        await state.set_state(UserState.deposit_hash)

        await msg.answer(
            f"{icon} <b>واریز {label}</b>\n"
            f"{'━'*28}\n"
            f"💵 مبلغ پرداختی:  <b>${amount:,.2f}</b>\n"
            f"📊 قیمت لحظه‌ای:  <b>{price_str}</b>\n"
            f"🌐 شبکه:          <b>{network}</b>\n"
            f"{'━'*28}\n\n"
            f"💰 <b>مبلغ ارسالی:</b>\n"
            f"<code>{coin_str} {sym}</code>\n\n"
            f"📤 <b>آدرس کیف پول:</b>\n"
            f"<code>{addr}</code>\n\n"
            f"<i>👆 روی مبلغ یا آدرس ضربه بزنید تا کپی شود</i>\n\n"
            f"{'━'*28}\n"
            f"✅ پس از واریز روی دکمه زیر بزنید و لینک هش تراکنش را ارسال کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ واریز کردم — ارسال لینک هش", callback_data="dep_send_hash")],
                [InlineKeyboardButton(text="❌ لغو واریز",                   callback_data="dep_cancel")],
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"deposit_amount error: {e}")
        await msg.answer(
            f"❌ خطای داخلی: <code>{type(e).__name__}: {str(e)[:200]}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
            ]),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "dep_send_hash")
async def dep_send_hash_prompt(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(UserState.deposit_hash)
    try:
        data     = await state.get_data()
        coin     = data.get("deposit_coin", {})
        addr     = coin.get("address", "—")
        label    = coin.get("label", "")
        icon     = coin.get("icon", "💳")
        coin_str = data.get("deposit_coin_amount", "")
        sym      = label.split()[0] if label else ""
        amount   = data.get("deposit_amount", 0)
        tries    = data.get("deposit_hash_tries", 0)
        warn     = f"\n\n⚠️ <b>تلاش {tries}/3</b> — لینک صحیح را ارسال کنید." if tries > 0 else ""
        await cb.message.edit_text(
            f"{icon} <b>واریز {label}</b>\n"
            f"{'━'*28}\n"
            f"💵 مبلغ: <b>${amount:,.2f}</b>\n\n"
            f"💰 <b>مبلغ ارسالی:</b>\n"
            f"<code>{coin_str} {sym}</code>\n\n"
            f"📤 <b>آدرس کیف پول:</b>\n"
            f"<code>{addr}</code>\n\n"
            f"{'━'*28}\n"
            f"🔗 <b>لینک هش تراکنش را ارسال کنید:</b>\n"
            f"<i>مثال: https://tronscan.org/#/transaction/abc...</i>"
            f"{warn}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
            ]),
            parse_mode="HTML"
        )
    except Exception:
        await cb.message.answer(
            "🔗 <b>لینک هش تراکنش را ارسال کنید:</b>\n<i>مثال: https://tronscan.org/#/transaction/abc...</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
            ]),
            parse_mode="HTML"
        )


@router.message(UserState.deposit_hash)
async def user_deposit_hash(msg: Message, state: FSMContext, db_user: User = None):
    try:
        tx_link = (msg.text or "").strip()
        if not tx_link:
            await msg.answer(
                "❌ لینک هش تراکنش نمی‌تواند خالی باشد.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ لغو واریز", callback_data="dep_cancel")]
                ])
            ); return

        data     = await state.get_data()
        amount   = data.get("deposit_amount", 0)
        coin     = data.get("deposit_coin", {})
        coin_str = data.get("deposit_coin_amount", "")
        coin_key = coin.get("key", "usdt_trc")
        method   = coin.get("label", "USDT")
        addr     = coin.get("address", "")
        sym      = method.split()[0] if method else ""
        tries    = data.get("deposit_hash_tries", 0)

        wait_msg = await msg.answer("🔍 <b>در حال بررسی تراکنش...</b>", parse_mode="HTML")

        from services.tx_verifier import verify_tx
        result = await verify_tx(tx_link, coin_key, addr, amount)

        # توکن جعلی — فوری رد
        if not result.is_real_token:
            await wait_msg.delete()
            await state.clear()
            await msg.answer(
                f"🚫 <b>واریز رد شد — توکن جعلی!</b>\n"
                f"{'━'*28}\n"
                f"❌ {result.error}\n\n"
                f"این تراکنش با توکن جعلی انجام شده و قابل قبول نیست.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📞 پشتیبانی", callback_data="user_support")],
                    [InlineKeyboardButton(text="🏠 بازگشت",   callback_data="user_home")],
                ]),
                parse_mode="HTML"
            ); return

        # وضعیت بررسی بات
        if result.ok:
            bot_status = "✅ تایید شد"
            bot_note   = "مبلغ و آدرس مقصد صحیح است."
        elif result.confirmed and not result.ok:
            bot_status = "⚠️ مغایرت دارد"
            bot_note   = result.error
        else:
            bot_status = "⏳ در انتظار تایید شبکه"
            bot_note   = result.error or "تراکنش هنوز در شبکه تایید نشده."

        # بررسی ناموفق — تا ۳ بار شانس
        if not result.ok and tries < 2:
            await wait_msg.delete()
            new_tries = tries + 1
            await state.update_data(deposit_hash_tries=new_tries)
            await msg.answer(
                f"⚠️ <b>بررسی بات: {bot_status}</b>\n"
                f"{'━'*28}\n"
                f"📋 {bot_note}\n\n"
                f"🔗 <a href=\"{result.explorer_url}\">مشاهده تراکنش</a>\n\n"
                f"{'━'*28}\n"
                f"تلاش <b>{new_tries}/3</b> — لینک صحیح را ارسال کنید یا واریز را لغو کنید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 ارسال مجدد لینک هش", callback_data="dep_send_hash")],
                    [InlineKeyboardButton(text="❌ لغو واریز",           callback_data="dep_cancel")],
                ]),
                parse_mode="HTML",
                disable_web_page_preview=True
            ); return

        # ثبت درخواست
        user_id = db_user.id if db_user else msg.from_user.id
        async with AsyncSessionLocal() as session:
            await create_deposit_request(
                session, user_id, amount, method, tx_link, addr,
                bot_verified=result.ok,
                bot_status=bot_status,
                bot_amount=result.amount,
                bot_currency=result.currency
            )
            await session.commit()
        await state.clear()
        await wait_msg.delete()

        await msg.answer(
            f"{'✅' if result.ok else '⚠️'} <b>درخواست واریز ثبت شد!</b>\n"
            f"{'━'*28}\n"
            f"💵 مبلغ:    <b>${amount:,.2f}</b>\n"
            f"💰 ارسالی: <b>{coin_str} {sym}</b>\n"
            f"🔗 <a href=\"{result.explorer_url}\">مشاهده تراکنش</a>\n"
            f"{'━'*28}\n\n"
            f"🤖 <b>بررسی بات:</b> {bot_status}\n"
            f"📋 {bot_note}\n\n"
            f"{'━'*28}\n"
            f"⏳ منتظر تایید نهایی ادمین باشید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت به خانه", callback_data="user_home")]
            ]),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.exception(f"deposit_hash error: {e}")
        await msg.answer(
            f"❌ خطای داخلی: <code>{type(e).__name__}: {str(e)[:200]}</code>",
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


# ── Orders — live tracking ───────────────────────────────────────────────────────────────────────────────
from datetime import datetime, timedelta, timezone as _tz

_ARCH_ST  = {'completed', 'cancelled', 'rejected'}
_ARCH_H   = 24
_ARCH_MAX = 30
_ST_MAP   = {
    'pending':    ('⏳', 'در صف'),
    'processing': ('🔄', 'در حال انجام'),
    'completed':  ('✅', 'تکمیل'),
    'partial':    ('⚠️', 'ناقص'),
    'rejected':   ('❌', 'رد'),
    'cancelled':  ('❌', 'کنسل'),
}


def _archived(o) -> bool:
    if getattr(o, 'status', '') not in _ARCH_ST:
        return False
    ts = getattr(o, 'updated_at', None) or getattr(o, 'created_at', None)
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_tz.utc)
    return datetime.now(_tz.utc) - ts > timedelta(hours=_ARCH_H)


@router.callback_query(F.data == 'user_orders')
async def user_orders(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from collections import defaultdict
    from services.panel_service import get_user_panel_orders
    async with AsyncSessionLocal() as session:
        all_smm   = await get_user_orders(session, db_user.id)
        all_panel = await get_user_panel_orders(session, db_user.id, limit=50)
        smm_label = await get_setting(session, 'smm_panel_title', 'SMMPass')
    smm_act   = [o for o in all_smm   if not _archived(o)]
    panel_act = [o for o in all_panel if not _archived(o)]
    buttons = []
    if not smm_act and not panel_act:
        await cb.message.edit_text(
            '📦 سفارش فعالی وجود ندارد.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🛒 سفارش جدید', callback_data='user_new_order_select')],
                [InlineKeyboardButton(text='📜 تاریخچه',        callback_data='user_orders_history')],
                [InlineKeyboardButton(text='🏠 بازگشت',            callback_data='user_home')],
            ])
        )
        return
    smm_grp   = defaultdict(list)
    panel_grp = defaultdict(list)
    for o in smm_act[:15]:
        smm_grp[getattr(o, 'panel_name', None) or smm_label].append(o)
    for o in panel_act[:15]:
        panel_grp[getattr(o, 'panel_name', None) or 'پنل دستی'].append(o)
    for pname, orders in smm_grp.items():
        buttons.append([InlineKeyboardButton(text=f'━━ 🤖 {pname} ━━', callback_data='noop')])
        for o in orders:
            ic, lb = _ST_MAP.get(o.status, ('🟡', o.status))
            buttons.append([InlineKeyboardButton(
                text=f'{ic} #{o.id}  {(o.service_name or "")[:24]}  —  {lb}',
                callback_data=f'user_order_{o.id}'
            )])
    for pname, orders in panel_grp.items():
        buttons.append([InlineKeyboardButton(text=f'━━ 🎛 {pname} ━━', callback_data='noop')])
        for o in orders:
            ic, lb = _ST_MAP.get(o.status, ('🟡', o.status))
            buttons.append([InlineKeyboardButton(
                text=f'{ic} #{o.id}  {(o.service_name or "")[:24]}  —  {lb}',
                callback_data=f'user_panel_order_{o.id}'
            )])
    buttons.append([
        InlineKeyboardButton(text='🛒 سفارش جدید', callback_data='user_new_order_select'),
        InlineKeyboardButton(text='📜 تاریخچه',        callback_data='user_orders_history'),
    ])
    buttons.append([InlineKeyboardButton(text='🏠 بازگشت', callback_data='user_home')])
    await cb.message.edit_text(
        '📦 <b>سفارش‌های فعال</b>',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='HTML'
    )




@router.callback_query(F.data == 'user_new_order_select')
async def user_new_order_select(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    await cb.message.edit_text(
        "🛒 <b>سفارش جدید</b>\n\nنوع سفارش را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 سفارش اتوماتیک (SMMPass)", callback_data="menu_smmpass")],
            [InlineKeyboardButton(text="🎛 سفارش دستی (پنل‌ها)",       callback_data="user_panels_menu")],
            [InlineKeyboardButton(text="🔙 بازگشت",                    callback_data="user_orders")],
        ]),
        parse_mode="HTML"
    )
@router.callback_query(F.data == 'user_orders_history')
async def user_orders_history(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from services.panel_service import get_user_panel_orders
    async with AsyncSessionLocal() as session:
        all_smm   = await get_user_orders(session, db_user.id)
        smm_label = await get_setting(session, 'smm_panel_title', 'SMMPass')
        all_panel = await get_user_panel_orders(session, db_user.id, limit=50)
    arch_smm   = [o for o in all_smm   if _archived(o)][:_ARCH_MAX]
    arch_panel = [o for o in all_panel if _archived(o)][:_ARCH_MAX]
    if not arch_smm and not arch_panel:
        await cb.message.edit_text(
            '📜 تاریخچه خالی است.',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='🔙 بازگشت', callback_data='user_orders')]
            ])
        )
        return
    buttons = []
    if arch_smm:
        buttons.append([InlineKeyboardButton(text=f'━━ 🤖 {pname} ━━', callback_data='noop')])
        for o in arch_smm:
            ic, lb = _ST_MAP.get(o.status, ('📌', o.status))
            buttons.append([InlineKeyboardButton(
                text=f'{ic} #{o.id}  {(o.service_name or "")[:22]}  —  {lb}',
                callback_data=f'user_order_{o.id}'
            )])
    if arch_panel:
        buttons.append([InlineKeyboardButton(text='━━ 🎛 پنل دستی ━━', callback_data='noop')])
        for o in arch_panel:
            ic, lb = _ST_MAP.get(o.status, ('📌', o.status))
            buttons.append([InlineKeyboardButton(
                text=f'{ic} #{o.id}  {(o.service_name or "")[:22]}  —  {lb}',
                callback_data=f'user_panel_order_{o.id}'
            )])
    buttons.append([InlineKeyboardButton(text='🔙 بازگشت', callback_data='user_orders')])
    await cb.message.edit_text(
        '📜 <b>تاریخچه سفارشات</b>',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith('user_panel_order_'))
async def user_panel_order_detail(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from html import escape
    from services.panel_service import get_panel_order
    try:
        order_id = int(cb.data.split('_')[-1])
    except (ValueError, IndexError):
        await cb.answer('❌ خطا', show_alert=True); return
    async with AsyncSessionLocal() as session:
        order = await get_panel_order(session, order_id)
    if not order or order.user_id != db_user.id:
        await cb.answer('سفارش یافت نشد!', show_alert=True); return
    ic, lb = _ST_MAP.get(order.status, ('🟡', order.status))
    sep = '━' * 22
    text = (
        f'🎛 <b>سفارش #{order.id}</b>  —  <b>{escape(order.panel_name or "")}</b>\n'
        f'{sep}\n'
        f'📌 {escape(order.service_name or "")}\n'
        f'🔗 <code>{escape(order.link or "")}</code>\n'
        f'🔢 {order.quantity:,}   💰 ${float(order.total_price):.4f}\n'
        f'📅 {order.created_at.strftime("%Y-%m-%d %H:%M")}\n'
        f'{sep}\n'
        f'{ic} <b>{lb}</b>\n'
    )
    if order.completed_qty is not None and order.status == 'partial':
        text += f'✅ انجام شده: <b>{order.completed_qty:,}</b>\n'
    if order.refund_amount and float(order.refund_amount) > 0:
        text += f'↩️ بازگشت: <b>${float(order.refund_amount):.4f}</b>\n'
    if order.admin_note:
        text += f'📝 {escape(order.admin_note)}\n'
    back = 'user_orders_history' if _archived(order) else 'user_orders'
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔙 بازگشت', callback_data=back)]
        ]),
        parse_mode='HTML'
    )


@router.callback_query(F.data.startswith('user_order_'))
async def user_order_detail(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from html import escape
    try:
        order_id = int(cb.data.split('_')[-1])
    except (ValueError, IndexError):
        await cb.answer('❌ خطا', show_alert=True); return
    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)
    if not order or order.user_id != db_user.id:
        await cb.answer('سفارش یافت نشد!', show_alert=True); return
    live_status  = order.status
    live_start   = order.start_count
    live_remains = order.remains
    api_error    = None
    try:
        api_data     = await get_order_status(order.service_id)
        live_status  = api_data.get('status', order.status).lower()
        live_start   = api_data.get('start_count', order.start_count)
        live_remains = api_data.get('remains', order.remains)
        async with AsyncSessionLocal() as session:
            from services.order_service import update_order_status, process_refund
            updated = await update_order_status(
                session, order_id, live_status,
                start_count=int(live_start)   if live_start   is not None else None,
                remains=int(live_remains)      if live_remains is not None else None,
            )
            if updated and live_status in ('cancelled', 'partial') and order.status != live_status:
                await process_refund(session, updated)
            await session.commit()
    except Exception as e:
        api_error = str(e)[:60]
    ic, lb = _ST_MAP.get(live_status, ('🟡', live_status))
    sep  = '━' * 22
    done = 0
    if live_start is not None and live_remains is not None:
        try: done = int(live_start) - int(live_remains)
        except Exception: done = 0
    pname = getattr(order, 'panel_name', None) or 'SMMPass'
    text = (
        f'📦 <b>سفارش #{order.id}</b>  —  <b>{escape(pname)}</b>\n'
        f'{sep}\n'
        f'📌 {escape(order.service_name or "")}\n'
        f'🔗 <code>{escape(order.link or "")}</code>\n'
        f'🔢 {order.quantity:,}   💰 ${float(order.sell_price):.4f}\n'
        f'📅 {order.created_at.strftime("%Y-%m-%d %H:%M")}\n'
        f'{sep}\n'
        f'{ic} <b>{lb}</b>\n'
    )
    if live_start is not None:
        text += f'🔢 شروع: <b>{int(live_start):,}</b>   ⏳ باقی: <b>{int(live_remains or 0):,}</b>\n'
    if done > 0:
        text += f'✅ انجام: <b>{done:,}</b>\n'
    if api_error:
        text += f'⚠️ <i>{escape(api_error)}</i>\n'
    back = 'user_orders_history' if _archived(order) else 'user_orders'
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🔄 بروزرسانی', callback_data=f'user_order_{order_id}')],
            [InlineKeyboardButton(text='🔙 بازگشت',    callback_data=back)],
        ]),
        parse_mode='HTML'
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
