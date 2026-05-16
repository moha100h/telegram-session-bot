"""
Admin panel — full featured.
Deposits approve/reject + user notification, users, orders, settings, SMMPass, broadcast.
"""
import logging, os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User
from services.user_service import (
    get_all_users, get_user_by_id, ban_user, unban_user,
    add_balance, deduct_balance, is_admin, get_all_admins,
)
from services.deposit_service import (
    get_pending_deposits, approve_deposit, reject_deposit,
)
from services.order_service import get_all_orders
from services.settings_service import get_setting as gs, set_setting as ss

logger   = logging.getLogger("admin")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


async def _is_admin(uid: int) -> bool:
    if uid == ADMIN_ID:
        return True
    async with AsyncSessionLocal() as session:
        return await is_admin(session, uid)


class AdminState(StatesGroup):
    set_setting_val   = State()
    manual_credit_uid = State()
    manual_credit_amt = State()
    search_user       = State()
    broadcast_text    = State()


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 کاربران",      callback_data="adm_users"),
         InlineKeyboardButton(text="📦 سفارش‌ها",     callback_data="adm_orders")],
        [InlineKeyboardButton(text="💳 واریزها",      callback_data="adm_deposits"),
         InlineKeyboardButton(text="⚙️ تنظیمات",     callback_data="adm_settings")],
        [InlineKeyboardButton(text="🚀 SMMPass",      callback_data="adm_smmpass"),
         InlineKeyboardButton(text="📢 همگانی",       callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 آمار",         callback_data="adm_stats")],
    ])


# ── Menu ──────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_admin")
async def admin_menu(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید.", show_alert=True); return
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "🔧 <b>پنل مدیریت</b>\n\nیک بخش را انتخاب کنید:",
        reply_markup=admin_menu_kb(), parse_mode="HTML"
    )


# ── Stats ─────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        users  = await get_all_users(session)
        orders = await get_all_orders(session)
        deps   = await get_pending_deposits(session)
    total_bal = sum(float(u.balance or 0) for u in users)
    total_rev = sum(float(o.sell_price or 0) for o in orders)
    completed = sum(1 for o in orders if o.status == "completed")
    await cb.message.edit_text(
        f"📊 <b>آمار کلی</b>\n\n"
        f"👥 کاربران: <b>{len(users)}</b>\n"
        f"📦 سفارشات: <b>{len(orders)}</b>  (✅ {completed} تکمیل)\n"
        f"💳 واریز در انتظار: <b>{len(deps)}</b>\n"
        f"💰 مجموع موجودی کاربران: <b>${total_bal:.2f}</b>\n"
        f"💹 مجموع درآمد: <b>${total_rev:.2f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
        ]),
        parse_mode="HTML"
    )


# ── Deposits ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_deposits")
async def adm_deposits(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        deps = await get_pending_deposits(session)
    if not deps:
        await cb.message.edit_text(
            "💳 <b>واریزها</b>\n\n✅ هیچ واریز در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
            ]),
            parse_mode="HTML"
        ); return
    buttons = []
    for dep in deps[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"💵 ${float(dep.amount):.2f} | {dep.method} | uid:{dep.user_id} | #{dep.id}",
            callback_data=f"adm_dep_{dep.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")])
    await cb.message.edit_text(
        f"💳 <b>واریزهای در انتظار</b> ({len(deps)} مورد)\n\nیک واریز را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_") & ~F.data.startswith("adm_dep_ok_") & ~F.data.startswith("adm_dep_no_"))
async def adm_dep_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    dep_id = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import Transaction
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Transaction).where(Transaction.id == dep_id))
        dep = res.scalar_one_or_none()
        if not dep:
            await cb.answer("واریز یافت نشد!", show_alert=True); return
        user = await get_user_by_id(session, dep.user_id)
    uname = f"@{user.username}" if user and user.username else f"uid:{dep.user_id}"
    await cb.message.edit_text(
        f"💳 <b>جزئیات واریز #{dep.id}</b>\n\n"
        f"👤 کاربر: <b>{uname}</b>\n"
        f"💵 مبلغ: <b>${float(dep.amount):.2f}</b>\n"
        f"🔧 روش: <b>{dep.method}</b>\n"
        f"🔗 هش: <code>{dep.tx_hash or '—'}</code>\n"
        f"📅 تاریخ: <b>{dep.created_at.strftime('%Y-%m-%d %H:%M')}</b>\n"
        f"⏳ وضعیت: <b>{dep.status}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید",   callback_data=f"adm_dep_ok_{dep_id}"),
             InlineKeyboardButton(text="❌ رد",      callback_data=f"adm_dep_no_{dep_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_deposits")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_ok_"))
async def adm_dep_approve(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    dep_id = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import Transaction
    async with AsyncSessionLocal() as session:
        ok, msg_txt = await approve_deposit(session, dep_id)
        await session.commit()
        if ok:
            res = await session.execute(select(Transaction).where(Transaction.id == dep_id))
            dep = res.scalar_one_or_none()
    if ok:
        await cb.answer("✅ تایید شد!", show_alert=True)
        if dep:
            try:
                await cb.bot.send_message(
                    dep.user_id,
                    f"✅ <b>واریز شما تایید شد!</b>\n"
                    f"💵 مبلغ <b>${float(dep.amount):.2f}</b> به حساب شما اضافه شد.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    else:
        await cb.answer(f"❌ {msg_txt}", show_alert=True)
    await adm_deposits(cb)


@router.callback_query(F.data.startswith("adm_dep_no_"))
async def adm_dep_reject(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    dep_id = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import Transaction
    async with AsyncSessionLocal() as session:
        ok, msg_txt = await reject_deposit(session, dep_id)
        await session.commit()
        if ok:
            res = await session.execute(select(Transaction).where(Transaction.id == dep_id))
            dep = res.scalar_one_or_none()
    if ok:
        await cb.answer("❌ رد شد.", show_alert=True)
        if dep:
            try:
                await cb.bot.send_message(
                    dep.user_id,
                    f"❌ <b>واریز شما رد شد.</b>\n"
                    f"💵 مبلغ: ${float(dep.amount):.2f} | روش: {dep.method}\n"
                    "برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    else:
        await cb.answer(f"❌ {msg_txt}", show_alert=True)
    await adm_deposits(cb)


# ── Users ─────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)
    await cb.message.edit_text(
        f"👥 <b>کاربران</b> ({len(users)} نفر)\n\nیک عملیات انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 جستجوی کاربر",      callback_data="adm_user_search")],
            [InlineKeyboardButton(text="💰 شارژ دستی",          callback_data="adm_manual_credit")],
            [InlineKeyboardButton(text="📋 لیست آخرین کاربران", callback_data="adm_users_list")],
            [InlineKeyboardButton(text="🔙 بازگشت",             callback_data="menu_admin")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_users_list")
async def adm_users_list(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)
    lines = []
    for u in users[:20]:
        status = "🚫" if u.is_banned else "✅"
        uname  = f"@{u.username}" if u.username else f"#{u.telegram_id}"
        lines.append(f"{status} <b>{u.display_name()}</b> {uname} | 💰${float(u.balance or 0):.2f}")
    await cb.message.edit_text(
        f"👥 <b>آخرین {min(20,len(users))} کاربر</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_user_search")
async def adm_user_search_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.search_user)
    await cb.message.edit_text("🔍 یوزرنیم یا آیدی عددی کاربر را وارد کنید:\n\n/cancel برای لغو")


@router.message(AdminState.search_user)
async def adm_user_search_handle(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    query = msg.text.strip().lstrip("@")
    await state.clear()
    from sqlalchemy import select
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        if query.isdigit():
            res = await session.execute(select(UserModel).where(UserModel.telegram_id == int(query)))
        else:
            res = await session.execute(select(UserModel).where(UserModel.username.ilike(f"%{query}%")))
        users = res.scalars().all()
    if not users:
        await msg.answer("❌ کاربری یافت نشد."); return
    buttons = []
    for u in users[:5]:
        uname = f"@{u.username}" if u.username else f"#{u.telegram_id}"
        buttons.append([InlineKeyboardButton(
            text=f"{u.display_name()} {uname} | ${float(u.balance or 0):.2f}",
            callback_data=f"adm_uid_{u.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")])
    await msg.answer(
        f"🔍 نتایج ({len(users)} مورد):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("adm_uid_"))
async def adm_user_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
    if not u:
        await cb.answer("کاربر یافت نشد!", show_alert=True); return
    uname = f"@{u.username}" if u.username else "—"
    await cb.message.edit_text(
        f"👤 <b>{u.display_name()}</b>\n\n"
        f"🆔 Telegram ID: <code>{u.telegram_id}</code>\n"
        f"👤 یوزرنیم: {uname}\n"
        f"📱 شماره: {u.phone or '—'}\n"
        f"💰 موجودی: <b>${float(u.balance or 0):.2f}</b>\n"
        f"🚫 وضعیت: {'مسدود' if u.is_banned else 'فعال'}\n"
        f"👥 دعوت‌ها: {u.referral_count}\n"
        f"📅 عضویت: {u.created_at.strftime('%Y-%m-%d')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 شارژ موجودی", callback_data=f"adm_credit_{u.id}"),
             InlineKeyboardButton(text="📦 سفارشات",     callback_data=f"adm_uorders_{u.id}")],
            [InlineKeyboardButton(
                text="🚫 مسدود کردن" if not u.is_banned else "✅ رفع مسدودی",
                callback_data=f"adm_toggleban_{u.id}"
            )],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_toggleban_"))
async def adm_toggle_ban(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
        if not u:
            await cb.answer("کاربر یافت نشد!", show_alert=True); return
        if u.is_banned:
            await unban_user(session, u.telegram_id)
            await cb.answer("✅ رفع مسدودی شد.")
        else:
            await ban_user(session, u.telegram_id)
            await cb.answer("🚫 مسدود شد.")
        await session.commit()
    # refresh detail
    cb.data = f"adm_uid_{uid}"
    await adm_user_detail(cb)


@router.callback_query(F.data.startswith("adm_credit_"))
async def adm_credit_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    uid = int(cb.data.split("_")[-1])
    await state.update_data(credit_uid=uid)
    await state.set_state(AdminState.manual_credit_amt)
    await cb.answer()
    await cb.message.edit_text("💰 مبلغ شارژ (دلار) را وارد کنید:\n\n/cancel برای لغو")


@router.message(AdminState.manual_credit_amt)
async def adm_credit_handle(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        amount = float(msg.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ مبلغ معتبر وارد کنید."); return
    data = await state.get_data()
    uid  = data.get("credit_uid")
    await state.clear()
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
        if not u:
            await msg.answer("❌ کاربر یافت نشد."); return
        await add_balance(session, u.id, amount)
        await session.commit()
    await msg.answer(
        f"✅ <b>${amount:.2f}</b> به کاربر <b>{u.display_name()}</b> اضافه شد.",
        parse_mode="HTML"
    )
    try:
        await msg.bot.send_message(
            u.telegram_id,
            f"💰 <b>${amount:.2f}</b> به موجودی شما اضافه شد.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data == "adm_manual_credit")
async def adm_manual_credit_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.manual_credit_uid)
    await cb.message.edit_text("💰 آیدی عددی تلگرام کاربر را وارد کنید:\n\n/cancel برای لغو")


@router.message(AdminState.manual_credit_uid)
async def adm_manual_credit_uid(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        tg_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ آیدی عددی وارد کنید."); return
    from sqlalchemy import select
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(UserModel).where(UserModel.telegram_id == tg_id))
        u   = res.scalar_one_or_none()
    if not u:
        await msg.answer("❌ کاربر یافت نشد."); return
    await state.update_data(credit_uid=u.id)
    await state.set_state(AdminState.manual_credit_amt)
    await msg.answer(
        f"👤 کاربر: <b>{u.display_name()}</b>\n"
        f"💰 موجودی فعلی: <b>${float(u.balance or 0):.2f}</b>\n\n"
        "مبلغ شارژ (دلار) را وارد کنید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_uorders_"))
async def adm_user_orders(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, uid)
        u      = await get_user_by_id(session, uid)
    if not orders:
        await cb.message.edit_text(
            "📦 این کاربر سفارشی ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_uid_{uid}")]
            ])
        ); return
    ST = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","cancelled":"❌","failed":"💔"}
    lines = []
    for o in orders[:10]:
        icon = ST.get(o.status, "🟡")
        lines.append(f"{icon} #{o.id} | {o.service_name[:20]} | {o.quantity:,} | ${float(o.sell_price):.4f}")
    await cb.message.edit_text(
        f"📦 سفارشات <b>{u.display_name() if u else uid}</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_uid_{uid}")]
        ]),
        parse_mode="HTML"
    )


# ── Orders ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_orders")
async def adm_orders(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        orders = await get_all_orders(session)
    ST = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","cancelled":"❌","failed":"💔"}
    lines = []
    for o in orders[:20]:
        icon = ST.get(o.status, "🟡")
        lines.append(
            f"{icon} <b>#{o.id}</b> uid:{o.user_id} | {o.service_name[:20]}\n"
            f"   🔢{o.quantity:,} 💰${float(o.sell_price):.4f} 📅{o.created_at.strftime('%m/%d %H:%M')}"
        )
    await cb.message.edit_text(
        f"📦 <b>آخرین سفارشات</b> ({len(orders)} کل)\n\n" + "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
        ]),
        parse_mode="HTML"
    )


# ── Settings ──────────────────────────────────────────────────────────────────
SETTING_KEYS = {
    "adm_set_bot_name":    ("bot_name",        "نام بات"),
    "adm_set_welcome":     ("welcome_message", "پیام خوش‌آمد"),
    "adm_set_support":     ("support_url",     "لینک پشتیبانی"),
    "adm_set_wallet_usdt": ("wallet_usdt",     "آدرس USDT"),
    "adm_set_wallet_ton":  ("wallet_ton",      "آدرس TON"),
    "adm_set_wallet_trx":  ("wallet_trx",      "آدرس TRX"),
    "adm_set_smm_title":   ("smm_panel_title", "نام دکمه SMM"),
    "adm_set_markup":      ("smm_markup_percent", "درصد سود SMM"),
}


@router.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        bot_name    = await gs(session, "bot_name", "SMM Panel")
        welcome     = await gs(session, "welcome_message", "خوش آمدید!")
        support_url = await gs(session, "support_url", "—")
        usdt_wallet = await gs(session, "wallet_usdt", "—")
        ton_wallet  = await gs(session, "wallet_ton", "—")
        trx_wallet  = await gs(session, "wallet_trx", "—")
        smm_title   = await gs(session, "smm_panel_title", "🚀 پنل SMM")
        markup      = await gs(session, "smm_markup_percent", "20")
    await cb.message.edit_text(
        f"⚙️ <b>تنظیمات</b>\n\n"
        f"🤖 نام بات: <b>{bot_name}</b>\n"
        f"👋 خوش‌آمد: <i>{welcome[:40]}</i>\n"
        f"📞 پشتیبانی: <b>{support_url}</b>\n"
        f"🟢 USDT: <code>{usdt_wallet}</code>\n"
        f"💎 TON: <code>{ton_wallet}</code>\n"
        f"⚡ TRX: <code>{trx_wallet}</code>\n"
        f"🚀 نام دکمه SMM: <b>{smm_title}</b>\n"
        f"💹 درصد سود: <b>{markup}%</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 نام بات",        callback_data="adm_set_bot_name"),
             InlineKeyboardButton(text="👋 خوش‌آمد",        callback_data="adm_set_welcome")],
            [InlineKeyboardButton(text="📞 پشتیبانی",       callback_data="adm_set_support"),
             InlineKeyboardButton(text="💹 درصد سود",       callback_data="adm_set_markup")],
            [InlineKeyboardButton(text="🟢 USDT",           callback_data="adm_set_wallet_usdt"),
             InlineKeyboardButton(text="💎 TON",            callback_data="adm_set_wallet_ton")],
            [InlineKeyboardButton(text="⚡ TRX",            callback_data="adm_set_wallet_trx"),
             InlineKeyboardButton(text="🚀 نام دکمه SMM",   callback_data="adm_set_smm_title")],
            [InlineKeyboardButton(text="🔙 بازگشت",         callback_data="menu_admin")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.in_(set(SETTING_KEYS.keys())))
async def adm_set_setting(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    key, label = SETTING_KEYS[cb.data]
    async with AsyncSessionLocal() as session:
        current = await gs(session, key, "—")
    await state.update_data(setting_key=key, setting_label=label)
    await state.set_state(AdminState.set_setting_val)
    await cb.message.edit_text(
        f"⚙️ <b>تنظیم: {label}</b>\n\nمقدار فعلی: <code>{current}</code>\n\nمقدار جدید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.set_setting_val)
async def adm_setting_val(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    data  = await state.get_data()
    key   = data.get("setting_key")
    label = data.get("setting_label", key)
    val   = (msg.text or "").strip()
    await state.clear()
    async with AsyncSessionLocal() as session:
        await ss(session, key, val)
        await session.commit()
    await msg.answer(
        f"✅ <b>{label}</b> به‌روز شد:\n<code>{val}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm_settings")]
        ]),
        parse_mode="HTML"
    )


# ── SMMPass Admin ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_smmpass")
async def adm_smmpass(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    from services.smmpass import get_services, get_balance, get_categories
    async with AsyncSessionLocal() as session:
        markup    = await gs(session, "smm_markup_percent", "20")
        smm_title = await gs(session, "smm_panel_title", "🚀 پنل SMM")
    try:
        bal_data = await get_balance()
        api_bal  = f"${bal_data.get('balance','?')} {bal_data.get('currency','USD')}"
    except Exception as e:
        api_bal = f"خطا: {e}"
    services = await get_services()
    cats     = get_categories(services)
    await cb.message.edit_text(
        f"🚀 <b>مدیریت SMMPass</b>\n\n"
        f"💰 موجودی API: <b>{api_bal}</b>\n"
        f"📊 سرویس‌ها: <b>{len(services)}</b> در <b>{len(cats)}</b> دسته\n"
        f"💹 درصد سود: <b>{markup}%</b>\n"
        f"🏷 نام دکمه: <b>{smm_title}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💹 درصد سود",      callback_data="adm_set_markup"),
             InlineKeyboardButton(text="🏷 نام دکمه",      callback_data="adm_set_smm_title")],
            [InlineKeyboardButton(text="📋 دسته‌بندی‌ها",  callback_data="adm_sp_cats"),
             InlineKeyboardButton(text="🔄 رفرش",          callback_data="adm_sp_refresh")],
            [InlineKeyboardButton(text="📦 سفارشات",       callback_data="adm_orders")],
            [InlineKeyboardButton(text="🔙 بازگشت",        callback_data="menu_admin")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_sp_refresh")
async def adm_sp_refresh(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer("در حال رفرش...")
    from services.smmpass import clear_cache, get_services
    clear_cache()
    services = await get_services(force=True)
    await cb.message.edit_text(
        f"✅ <b>سرویس‌ها رفرش شدند</b>\n📊 تعداد: <b>{len(services)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_smmpass")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_sp_cats")
async def adm_sp_cats(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    from services.smmpass import get_services, get_categories
    async with AsyncSessionLocal() as session:
        markup = float(await gs(session, "smm_markup_percent", "20"))
    services = await get_services()
    cats     = get_categories(services)
    lines = []
    for cat, svcs in list(cats.items())[:15]:
        rates    = [float(s.get("rate", 0)) for s in svcs]
        min_r    = min(rates); max_r = max(rates)
        sell_min = round(min_r * (1 + markup/100), 4)
        sell_max = round(max_r * (1 + markup/100), 4)
        short    = cat.replace("TG - ", "")[:30]
        lines.append(
            f"📌 <b>{short}</b> ({len(svcs)})\n"
            f"   API: ${min_r:.4f}–${max_r:.4f} | فروش: ${sell_min:.4f}–${sell_max:.4f}"
        )
    text = f"📋 <b>دسته‌بندی‌ها</b> (سود {markup:.0f}%)\n\n" + "\n\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n..."
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_smmpass")]
        ]),
        parse_mode="HTML"
    )


# ── Broadcast ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.broadcast_text)
    await cb.message.edit_text(
        "📢 <b>پیام همگانی</b>\n\nمتن پیام را وارد کنید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.broadcast_text)
async def adm_broadcast_send(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    text = msg.text or ""
    await state.clear()
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)
    sent = failed = 0
    for u in users:
        try:
            await msg.bot.send_message(u.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await msg.answer(
        f"📢 <b>ارسال تمام شد</b>\n✅ موفق: {sent} | ❌ ناموفق: {failed}",
        parse_mode="HTML"
    )


# ── Admins list ───────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_admins")
async def adm_admins(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        admins = await get_all_admins(session)
    lines = [f"👑 <b>سوپرادمین</b>: <code>{ADMIN_ID}</code>"]
    for a in admins:
        uname = f"@{a.username}" if a.username else f"ID:{a.telegram_id}"
        lines.append(f"🔑 {uname} | نقش: {a.role}")
    await cb.message.edit_text(
        "🔑 <b>ادمین‌ها</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
        ]),
        parse_mode="HTML"
    )
