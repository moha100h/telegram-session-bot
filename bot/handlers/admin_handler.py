import json
import os
import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from db.database import AsyncSessionLocal
from db.models import User, AdminUser, Transaction, Order
from services.user_service import (
    get_user, get_admin, get_all_admins, add_admin, remove_admin,
    ban_user, unban_user, add_balance, deduct_balance, get_all_users
)
from services.deposit_service import approve_deposit, reject_deposit, get_pending_deposits
from services.settings_service import get_setting, set_setting, get_all_settings
from services.order_service import get_all_orders
from db.models import Transaction as Tx

logger = logging.getLogger("admin")
router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class AdminState(StatesGroup):
    add_admin_id     = State()
    remove_admin_id  = State()
    broadcast_text   = State()
    add_balance_id   = State()
    add_balance_amt  = State()
    set_setting_key  = State()
    set_setting_val  = State()
    manual_credit_id = State()
    manual_credit_amt= State()


def is_super(telegram_id: int) -> bool:
    return telegram_id == ADMIN_ID


async def check_admin(cb: CallbackQuery) -> bool:
    if is_super(cb.from_user.id):
        return True
    async with AsyncSessionLocal() as session:
        adm = await get_admin(session, cb.from_user.id)
        return adm is not None


# ─── Admin menu ──────────────────────────────────────────────────────────────
def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 کاربران",        callback_data="adm_users"),
         InlineKeyboardButton(text="📦 سفارش‌ها",       callback_data="adm_orders")],
        [InlineKeyboardButton(text="💳 واریزها",        callback_data="adm_deposits"),
         InlineKeyboardButton(text="⚙️ تنظیمات",       callback_data="adm_settings")],
        [InlineKeyboardButton(text="🔑 ادمین‌ها",       callback_data="adm_admins"),
         InlineKeyboardButton(text="📢 پیام همگانی",    callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 آمار",           callback_data="adm_stats")],
    ])


@router.callback_query(F.data == "menu_admin")
async def admin_menu(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔ دسترسی ندارید.", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text(
        "🔧 <b>پنل مدیریت</b>\n\nیک بخش را انتخاب کنید:",
        reply_markup=admin_menu_kb(), parse_mode="HTML"
    )


# ─── Stats ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        total_users  = (await session.execute(func.count(User.id).select())).scalar() or 0
        banned       = (await session.execute(select(func.count()).where(User.is_banned == True))).scalar() or 0
        total_orders = (await session.execute(select(func.count()).select_from(Order))).scalar() or 0
        pending_deps = (await session.execute(
            select(func.count()).select_from(Tx).where(Tx.type == "deposit", Tx.status == "pending")
        )).scalar() or 0
        total_dep = (await session.execute(
            select(func.sum(Tx.amount)).where(Tx.type == "deposit", Tx.status == "approved")
        )).scalar() or 0

    text = (
        "📊 <b>آمار کلی</b>\n\n"
        f"👥 کاربران: <b>{total_users}</b> (مسدود: {banned})\n"
        f"📦 سفارش‌ها: <b>{total_orders}</b>\n"
        f"⏳ واریزی در انتظار: <b>{pending_deps}</b>\n"
        f"💰 کل واریزی: <b>${float(total_dep):.2f}</b>\n"
    )
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
    ]), parse_mode="HTML")


# ─── Deposits ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_deposits")
async def adm_deposits(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        pending = await get_pending_deposits(session)

    if not pending:
        await cb.message.edit_text(
            "✅ هیچ واریز در انتظاری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
            ])
        )
        return

    buttons = []
    for tx in pending[:10]:
        buttons.append([InlineKeyboardButton(
            text=f"#{tx.id} | ${float(tx.amount):.2f} | {tx.method}",
            callback_data=f"adm_dep_{tx.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")])
    await cb.message.edit_text(
        f"💳 <b>واریزهای در انتظار ({len(pending)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_"))
async def adm_dep_detail(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    tx_id = int(cb.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        tx = await session.get(Tx, tx_id)
        if not tx:
            await cb.message.edit_text("❌ واریز یافت نشد.")
            return
        user = await session.get(User, tx.user_id)
        uname = user.display_name() if user else "?"

    text = (
        f"💳 <b>واریز #{tx_id}</b>\n\n"
        f"👤 {uname} (@{user.username or '-'})\n"
        f"💵 مبلغ: <b>${float(tx.amount):.4f}</b>\n"
        f"💳 روش: {tx.method}\n"
        f"🔗 Hash: <code>{tx.tx_hash or '-'}</code>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید",  callback_data=f"adm_dep_ok_{tx_id}"),
         InlineKeyboardButton(text="❌ رد",     callback_data=f"adm_dep_no_{tx_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_deposits")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_dep_ok_"))
async def adm_dep_approve(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    tx_id = int(cb.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        ok = await approve_deposit(session, tx_id)
        if ok:
            tx = await session.get(Tx, tx_id)
            await cb.message.edit_text(
                f"✅ <b>واریز #{tx_id} تایید شد.</b>\n"
                f"💰 ${float(tx.amount):.4f} به حسابتان اضافه شد.",
                parse_mode="HTML"
            )
        else:
            await cb.message.edit_text("❌ خطا در تایید واریز.")


@router.callback_query(F.data.startswith("adm_dep_no_"))
async def adm_dep_reject(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    tx_id = int(cb.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        await reject_deposit(session, tx_id)
    await cb.message.edit_text(f"❌ واریز #{tx_id} رد شد.")


# ─── Users ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)

    if not users:
        await cb.message.edit_text("هیچ کاربری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
            ]))
        return

    buttons = []
    for u in users[:15]:
        label = f"{u.display_name()} | ${float(u.balance or 0):.2f}"
        if u.is_banned:
            label = "🚫 " + label
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"adm_user_{u.telegram_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")])
    await cb.message.edit_text(
        f"👥 <b>کاربران ({len(users)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_user_"))
async def adm_user_detail(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    tg_id = int(cb.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        user = await get_user(session, tg_id)
        if not user:
            await cb.message.edit_text("❌ کاربر یافت نشد.")
            return
        order_count = (await session.execute(
            select(func.count()).select_from(Order).where(Order.user_id == user.id)
        )).scalar() or 0

    text = (
        f"👤 <b>{user.display_name()}</b>\n\n"
        f"🔹 @{user.username or '-'}\n"
        f"🟢 ID: <code>{user.telegram_id}</code>\n"
        f"📱 شماره: {user.phone or '—'}\n"
        f"💰 موجودی: <b>${float(user.balance or 0):.2f}</b>\n"
        f"📦 سفارش‌ها: {order_count}\n"
        f"🚫 مسدود: {'بله' if user.is_banned else 'خیر'}"
    )
    ban_btn = "✅ رفع مسدودی" if user.is_banned else "🚫 مسدود کردن"
    ban_cb  = f"adm_unban_{tg_id}" if user.is_banned else f"adm_ban_{tg_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=ban_btn,           callback_data=ban_cb),
         InlineKeyboardButton(text="💰 افزایش موجودی", callback_data=f"adm_addbal_{tg_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت",        callback_data="adm_users")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_ban_"))
async def adm_ban(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    tg_id = int(cb.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        await ban_user(session, tg_id)
    await cb.answer("✅ کاربر مسدود شد.", show_alert=True)
    await adm_users(cb)


@router.callback_query(F.data.startswith("adm_unban_"))
async def adm_unban(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    tg_id = int(cb.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        await unban_user(session, tg_id)
    await cb.answer("✅ رفع مسدودی شد.", show_alert=True)
    await adm_users(cb)


@router.callback_query(F.data.startswith("adm_addbal_"))
async def adm_addbal_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    tg_id = int(cb.data.split("_")[2])
    await state.update_data(target_tg_id=tg_id)
    await state.set_state(AdminState.add_balance_amt)
    await cb.answer()
    await cb.message.answer(f"💰 مقدار افزایش موجودی برای کاربر <code>{tg_id}</code> را وارد کنید (دلار):", parse_mode="HTML")


@router.message(AdminState.add_balance_amt)
async def adm_addbal_do(msg: Message, state: FSMContext):
    data = await state.get_data()
    tg_id = data.get("target_tg_id")
    try:
        amount = float(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد معتبر وارد کنید.")
        return
    async with AsyncSessionLocal() as session:
        user = await get_user(session, tg_id)
        if user:
            await add_balance(session, user.id, amount)
            await msg.answer(f"✅ ${amount:.2f} به کاربر <code>{tg_id}</code> اضافه شد.", parse_mode="HTML")
        else:
            await msg.answer("❌ کاربر یافت نشد.")
    await state.clear()


# ─── Orders ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_orders")
async def adm_orders(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        orders = await get_all_orders(session)

    if not orders:
        await cb.message.edit_text("هیچ سفارشی وجود ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
            ]))
        return

    buttons = []
    for o in orders[:15]:
        buttons.append([InlineKeyboardButton(
            text=f"#{o.id} | {o.status} | ${float(o.sell_price):.2f}",
            callback_data=f"adm_order_{o.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")])
    await cb.message.edit_text(
        f"📦 <b>سفارش‌ها ({len(orders)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


# ─── Settings ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        s = await get_all_settings(session)

    text = (
        "⚙️ <b>تنظیمات</b>\n\n"
        f"📈 Markup: <b>{s.get('smm_markup_percent','20')}%</b>\n"
        f"🟢 USDT: <code>{s.get('usdt_wallet','—')[:20]}</code>\n"
        f"💎 TON: <code>{s.get('ton_wallet','—')[:20]}</code>\n"
        f"⚡ TRX: <code>{s.get('trx_wallet','—')[:20]}</code>\n"
        f"💬 پشتیبانی: @{s.get('support_username','—')}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش تنظیم", callback_data="adm_set_edit")],
        [InlineKeyboardButton(text="🔙 بازگشت",       callback_data="menu_admin")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "adm_set_edit")
async def adm_set_edit_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    await state.set_state(AdminState.set_setting_key)
    await cb.message.answer(
        "🔑 کلید تنظیم را وارد کنید:\n"
        "مثال: <code>smm_markup_percent</code>, <code>usdt_wallet</code>, "
        "<code>ton_wallet</code>, <code>trx_wallet</code>, <code>support_username</code>",
        parse_mode="HTML"
    )


@router.message(AdminState.set_setting_key)
async def adm_set_key(msg: Message, state: FSMContext):
    await state.update_data(setting_key=msg.text.strip())
    await state.set_state(AdminState.set_setting_val)
    await msg.answer(f"📝 مقدار جدید برای <code>{msg.text.strip()}</code> را وارد کنید:", parse_mode="HTML")


@router.message(AdminState.set_setting_val)
async def adm_set_val(msg: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("setting_key", "")
    async with AsyncSessionLocal() as session:
        await set_setting(session, key, msg.text.strip())
    await msg.answer(f"✅ تنظیم <code>{key}</code> ذخیره شد.", parse_mode="HTML")
    await state.clear()


# ─── Admins ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_admins")
async def adm_admins(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔ فقط سوپر ادمین.", show_alert=True)
        return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        admins = await get_all_admins(session)

    buttons = []
    for a in admins:
        buttons.append([InlineKeyboardButton(
            text=f"@{a.username or a.telegram_id} | {a.role}",
            callback_data=f"adm_adm_{a.telegram_id}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ افزودن ادمین", callback_data="adm_adm_add")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت",       callback_data="menu_admin")])
    await cb.message.edit_text(
        f"🔑 <b>ادمین‌ها ({len(admins)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_adm_add")
async def adm_adm_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    await state.set_state(AdminState.add_admin_id)
    await cb.message.answer("🆔 آیدی تلگرام ادمین جدید را وارد کنید:")


@router.message(AdminState.add_admin_id)
async def adm_adm_add_do(msg: Message, state: FSMContext):
    try:
        tg_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ آیدی معتبر وارد کنید.")
        return
    async with AsyncSessionLocal() as session:
        await add_admin(session, tg_id)
    await msg.answer(f"✅ ادمین جدید با ID <code>{tg_id}</code> اضافه شد.", parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("adm_adm_") & ~F.data.in_({"adm_adm_add"}))
async def adm_adm_detail(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    tg_id = int(cb.data.split("_")[2])
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, tg_id)
        if not admin:
            await cb.message.edit_text("❌ ادمین یافت نشد.")
            return
        perms = admin.all_perms()

    perm_text = "\n".join([(f"  ✅ {k}" if v else f"  ❌ {k}") for k, v in perms.items()]) or "  (بدون دسترسی خاص)"
    text = (
        f"🔑 <b>{admin.username or admin.telegram_id}</b>\n"
        f"🟢 ID: <code>{admin.telegram_id}</code>\n"
        f"🏷 نقش: {admin.role}\n\n"
        f"🔐 دسترسی‌ها:\n{perm_text}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 حذف ادمین", callback_data=f"adm_adm_del_{tg_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت",   callback_data="adm_admins")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_adm_del_"))
async def adm_adm_del(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    tg_id = int(cb.data.split("_")[3])
    async with AsyncSessionLocal() as session:
        removed = await remove_admin(session, tg_id)
    if removed:
        await cb.answer("✅ ادمین حذف شد.", show_alert=True)
    else:
        await cb.answer("❌ ادمین یافت نشد.", show_alert=True)
    await adm_admins(cb)


# ─── Broadcast ───────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔", show_alert=True)
        return
    await cb.answer()
    await state.set_state(AdminState.broadcast_text)
    await cb.message.answer("📢 متن پیام همگانی را وارد کنید:")


@router.message(AdminState.broadcast_text)
async def adm_broadcast_do(msg: Message, state: FSMContext):
    from aiogram import Bot
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)

    bot: Bot = msg.bot
    sent = 0
    for u in users:
        try:
            await bot.send_message(u.telegram_id, msg.text)
            sent += 1
        except Exception:
            pass

    await msg.answer(f"✅ پیام به {sent} کاربر ارسال شد.")
    await state.clear()
