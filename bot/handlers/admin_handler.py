"""
Admin panel handler.
"""
import json
import os
import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
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

logger   = logging.getLogger("admin")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class AdminState(StatesGroup):
    add_admin_id   = State()
    add_admin_role = State()
    credit_uid     = State()
    credit_amount  = State()
    debit_uid      = State()
    debit_amount   = State()
    set_value      = State()
    broadcast_msg  = State()
    search_user    = State()
    ban_uid        = State()
    unban_uid      = State()


def is_super(tg_id: int) -> bool:
    return tg_id == ADMIN_ID


async def check_admin_cb(cb: CallbackQuery, perm: str = None) -> bool:
    if is_super(cb.from_user.id): return True
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, cb.from_user.id)
        if not admin:
            await cb.answer("⛔️ دسترسی ندارید.", show_alert=True)
            return False
        if perm and not admin.has_perm(perm):
            await cb.answer(f"⛔️ دسترسی {perm} ندارید.", show_alert=True)
            return False
    return True


async def check_admin_msg(msg: Message) -> bool:
    if is_super(msg.from_user.id): return True
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, msg.from_user.id)
        return admin is not None


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 آمار",              callback_data="adm_stats")],
        [InlineKeyboardButton(text="👥 کاربران",          callback_data="adm_users")],
        [InlineKeyboardButton(text="⏳ واریزی‌های در انتظار",  callback_data="adm_pending_deps")],
        [InlineKeyboardButton(text="📦 سفارش‌ها",          callback_data="adm_orders")],
        [InlineKeyboardButton(text="🔑 ادمین‌ها",          callback_data="adm_admins")],
        [InlineKeyboardButton(text="⚙️ تنظیمات",          callback_data="adm_settings")],
        [InlineKeyboardButton(text="📢 پخش همگانی",       callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🏠 بازگشت",           callback_data="user_home")],
    ])


@router.callback_query(F.data == "menu_admin")
async def adm_entry(cb: CallbackQuery, state: FSMContext):
    if not await check_admin_cb(cb): return
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🔑 <b>پنل مدیریت</b>\nیک بخش را انتخاب کنید:",
        reply_markup=admin_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_menu")
async def adm_menu_back(cb: CallbackQuery, state: FSMContext):
    if not await check_admin_cb(cb): return
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🔑 <b>پنل مدیریت</b>\nیک بخش را انتخاب کنید:",
        reply_markup=admin_kb(), parse_mode="HTML"
    )


# ─ Stats ────────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    if not await check_admin_cb(cb): return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        total_users  = (await session.execute(select(func.count(User.id)))).scalar()
        banned       = (await session.execute(select(func.count(User.id)).where(User.is_banned == True))).scalar()
        total_orders = (await session.execute(select(func.count(Order.id)))).scalar()
        pending_deps = (await session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.type == "deposit", Transaction.status == "pending"
            )
        )).scalar()
        total_dep = (await session.execute(
            select(func.sum(Transaction.amount)).where(
                Transaction.type == "deposit", Transaction.status == "approved"
            )
        )).scalar() or 0
        markup = await get_setting(session, "smm_markup_percent", "20")

    await cb.message.edit_text(
        "📊 <b>آمار کلی</b>\n\n"
        f"👥 کاربران: <b>{total_users}</b> (مسدود: {banned})\n"
        f"📦 سفارش‌ها: <b>{total_orders}</b>\n"
        f"⏳ واریزی در انتظار: <b>{pending_deps}</b>\n"
        f"💰 کل واریزی: <b>${float(total_dep):.2f}</b>\n"
        f"📈 Markup: <b>{markup}%</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu")]
        ]), parse_mode="HTML"
    )


# ─ Pending deposits ─────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_pending_deps")
async def adm_pending_deps(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_deposits"): return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        txs = await get_pending_deposits(session)

    if not txs:
        await cb.message.edit_text(
            "✅ هیچ واریزی در انتظار نیست.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu")]
            ])
        )
        return

    rows = []
    async with AsyncSessionLocal() as session:
        for tx in txs:
            user = await session.get(User, tx.user_id)
            uname = user.display_name()[:12] if user else f"ID:{tx.user_id}"
            rows.append([InlineKeyboardButton(
                text=f"${float(tx.amount):.2f} | {tx.method} | {uname}",
                callback_data=f"adm_dep_view_{tx.id}"
            )])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu")])

    await cb.message.edit_text(
        f"⏳ <b>واریزی‌های در انتظار ({len(txs)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_view_"))
async def adm_dep_view(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_deposits"): return
    await cb.answer()
    tx_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        tx   = await session.get(Transaction, tx_id)
        if not tx: return
        user = await session.get(User, tx.user_id)

    uname = user.display_name() if user else f"ID:{tx.user_id}"
    await cb.message.edit_text(
        f"💰 <b>واریز #{tx_id}</b>\n\n"
        f"👤 {uname} (@{user.username or '-'})\n"
        f"💵 مبلغ: <b>${float(tx.amount):.4f}</b>\n"
        f"💳 روش: {tx.method}\n"
        f"🔗 Hash: <code>{tx.tx_hash or '-'}</code>\n"
        f"📅 {tx.created_at.strftime('%Y-%m-%d %H:%M')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید", callback_data=f"adm_dep_ok_{tx_id}"),
             InlineKeyboardButton(text="❌ رد",    callback_data=f"adm_dep_no_{tx_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_pending_deps")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_ok_"))
async def adm_dep_ok(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_deposits"): return
    await cb.answer()
    tx_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        ok, msg_text = await approve_deposit(session, tx_id)
        if not ok:
            await cb.answer(f"❌ {msg_text}", show_alert=True); return
        tx   = await session.get(Transaction, tx_id)
        user = await session.get(User, tx.user_id)

    await cb.message.edit_text(
        f"✅ <b>واریز #{tx_id} تایید شد.</b>\n"
        f"💰 ${float(tx.amount):.4f} به حساب کاربر اضافه شد.",
        parse_mode="HTML"
    )
    try:
        await cb.bot.send_message(
            user.telegram_id,
            f"✅ <b>واریز تایید شد!</b>\n💰 ${float(tx.amount):.4f} به حسابتان اضافه شد.",
            parse_mode="HTML"
        )
    except Exception: pass


@router.callback_query(F.data.startswith("adm_dep_no_"))
async def adm_dep_no(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_deposits"): return
    await cb.answer()
    tx_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        ok, msg_text = await reject_deposit(session, tx_id)
        if not ok:
            await cb.answer(f"❌ {msg_text}", show_alert=True); return
        tx   = await session.get(Transaction, tx_id)
        user = await session.get(User, tx.user_id)

    await cb.message.edit_text(f"❌ <b>واریز #{tx_id} رد شد.</b>", parse_mode="HTML")
    try:
        await cb.bot.send_message(
            user.telegram_id,
            "❌ <b>واریز شما رد شد.</b>\nلطفاً با پشتیبانی تماس بگیرید.",
            parse_mode="HTML"
        )
    except Exception: pass


# ─ Users ─────────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_users"): return
    await cb.answer()
    await cb.message.edit_text(
        "👥 <b>مدیریت کاربران</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 جستجو کاربر",    callback_data="adm_search_user")],
            [InlineKeyboardButton(text="🚫 بن کاربر",        callback_data="adm_ban_start")],
            [InlineKeyboardButton(text="✅ انبن کاربر",       callback_data="adm_unban_start")],
            [InlineKeyboardButton(text="💸 شارژ دستی",       callback_data="adm_credit_start")],
            [InlineKeyboardButton(text="💸 کسر موجودی",     callback_data="adm_debit_start")],
            [InlineKeyboardButton(text="🔙 بازگشت",           callback_data="adm_menu")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_search_user")
async def adm_search_user(cb: CallbackQuery, state: FSMContext):
    if not await check_admin_cb(cb, "manage_users"): return
    await cb.answer()
    await state.set_state(AdminState.search_user)
    await cb.message.edit_text("🔍 شناسه تلگرام یا یوزرنیم وارد کنید:")


@router.message(AdminState.search_user)
async def adm_search_user_handle(msg: Message, state: FSMContext):
    if not await check_admin_msg(msg): return
    await state.clear()
    q = (msg.text or "").strip()
    async with AsyncSessionLocal() as session:
        try:
            tg_id = int(q)
            r = await session.execute(select(User).where(User.telegram_id == tg_id))
        except ValueError:
            r = await session.execute(select(User).where(User.username.ilike(f"%{q}%")))
        users = list(r.scalars().all())

    if not users:
        await msg.answer("❌ کاربری یافت نشد."); return

    rows = []
    for u in users[:10]:
        icon = "🚫" if u.is_banned else "✅"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {u.display_name()[:15]} | ${float(u.balance or 0):.2f}",
            callback_data=f"adm_user_view_{u.id}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")])
    await msg.answer(
        f"🔍 {len(users)} کاربر یافت شد:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


@router.callback_query(F.data.startswith("adm_user_view_"))
async def adm_user_view(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_users"): return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if not user: return
        order_count = (await session.execute(
            select(func.count(Order.id)).where(Order.user_id == uid)
        )).scalar()

    ban_st = "🚫 مسدود" if user.is_banned else "✅ فعال"
    await cb.message.edit_text(
        f"👤 <b>{user.display_name()}</b>\n\n"
        f"📎 @{user.username or '-'}\n"
        f"🔢 ID: <code>{user.telegram_id}</code>\n"
        f"📱 شماره: {user.phone or '❌'}\n"
        f"💰 موجودی: <b>${float(user.balance or 0):.2f}</b>\n"
        f"📦 سفارش‌ها: {order_count}\n"
        f"🔴 وضعیت: {ban_st}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 بن",  callback_data=f"adm_do_ban_{user.telegram_id}"),
             InlineKeyboardButton(text="✅ انبن", callback_data=f"adm_do_unban_{user.telegram_id}")],
            [InlineKeyboardButton(text="💸 شارژ", callback_data=f"adm_do_credit_{uid}"),
             InlineKeyboardButton(text="💸 کسر",  callback_data=f"adm_do_debit_{uid}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_do_ban_"))
async def adm_do_ban(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_users"): return
    tg_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await ban_user(session, tg_id)
    await cb.answer("🚫 کاربر بن شد.", show_alert=True)


@router.callback_query(F.data.startswith("adm_do_unban_"))
async def adm_do_unban(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_users"): return
    tg_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await unban_user(session, tg_id)
    await cb.answer("✅ کاربر انبن شد.", show_alert=True)


@router.callback_query(F.data.startswith("adm_do_credit_"))
async def adm_do_credit_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin_cb(cb, "manage_users"): return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    await state.set_state(AdminState.credit_amount)
    await state.update_data(target_uid=uid)
    await cb.message.edit_text(f"💸 مبلغ شارژ (دلار) برای کاربر #{uid}:")


@router.message(AdminState.credit_amount)
async def adm_credit_amount(msg: Message, state: FSMContext):
    if not await check_admin_msg(msg): return
    try: amount = float(msg.text.strip())
    except: await msg.answer("❌ عدد صحیح."); return
    data = await state.get_data(); await state.clear()
    async with AsyncSessionLocal() as session:
        user = await session.get(User, data["target_uid"])
        await add_balance(session, data["target_uid"], amount)
        from db.models import Transaction as Tx
        session.add(Tx(user_id=data["target_uid"], type="manual", amount=amount,
                       status="approved", description="Manual credit by admin"))
    await msg.answer(f"✅ ${amount} به حساب کاربر اضافه شد.")
    try: await msg.bot.send_message(user.telegram_id, f"✅ موجودی شما ${amount} شارژ شد.")
    except: pass


@router.callback_query(F.data.startswith("adm_do_debit_"))
async def adm_do_debit_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin_cb(cb, "manage_users"): return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    await state.set_state(AdminState.debit_amount)
    await state.update_data(target_uid=uid)
    await cb.message.edit_text(f"💸 مبلغ کسر (دلار) برای کاربر #{uid}:")


@router.message(AdminState.debit_amount)
async def adm_debit_amount(msg: Message, state: FSMContext):
    if not await check_admin_msg(msg): return
    try: amount = float(msg.text.strip())
    except: await msg.answer("❌ عدد صحیح."); return
    data = await state.get_data(); await state.clear()
    async with AsyncSessionLocal() as session:
        ok = await deduct_balance(session, data["target_uid"], amount)
        if not ok: await msg.answer("❌ موجودی کافی نیست."); return
        from db.models import Transaction as Tx
        session.add(Tx(user_id=data["target_uid"], type="manual", amount=-amount,
                       status="approved", description="Manual debit by admin"))
    await msg.answer(f"✅ ${amount} از حساب کاربر کسر شد.")


# ─ Admins management ────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_admins")
async def adm_admins(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️ فقط سوپرادمین.", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        admins = await get_all_admins(session)

    rows = []
    for a in admins:
        rows.append([InlineKeyboardButton(
            text=f"🔑 {a.username or a.telegram_id} | {a.role}",
            callback_data=f"adm_admin_view_{a.id}"
        )])
    rows.append([InlineKeyboardButton(text="➕ اضافه ادمین", callback_data="adm_add_admin")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu")])
    await cb.message.edit_text(
        f"🔑 <b>ادمین‌ها ({len(admins)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.add_admin_id)
    await cb.message.edit_text("➕ شناسه تلگرام ادمین جدید را وارد کنید:")


@router.message(AdminState.add_admin_id)
async def adm_add_admin_id(msg: Message, state: FSMContext):
    if not is_super(msg.from_user.id): return
    try: tg_id = int(msg.text.strip())
    except: await msg.answer("❌ شناسه عددی."); return
    await state.update_data(new_admin_id=tg_id)
    await state.set_state(AdminState.add_admin_role)
    await msg.answer(
        "نقش را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 admin",     callback_data="adm_role_admin")],
            [InlineKeyboardButton(text="🛡 moderator", callback_data="adm_role_moderator")],
            [InlineKeyboardButton(text="📞 support",   callback_data="adm_role_support")],
        ])
    )


@router.callback_query(F.data.startswith("adm_role_"))
async def adm_add_admin_role(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    role = cb.data[9:]
    data = await state.get_data(); await state.clear()
    tg_id = data.get("new_admin_id")
    perms = {
        "admin":     {"manage_users": True, "manage_orders": True, "manage_deposits": True, "view_stats": True},
        "moderator": {"manage_users": True, "manage_orders": True, "manage_deposits": False, "view_stats": True},
        "support":   {"manage_users": False, "manage_orders": False, "manage_deposits": False, "view_stats": True},
    }.get(role, {})
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(AdminUser).where(AdminUser.telegram_id == tg_id))).scalar_one_or_none()
        if existing:
            await cb.message.edit_text("❌ این کاربر قبلاً ادمین است."); return
        await add_admin(session, tg_id, "", role, perms)
    await cb.message.edit_text(
        f"✅ ادمین جدید با نقش <b>{role}</b> اضافه شد.\n🔢 ID: <code>{tg_id}</code>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_admin_view_"))
async def adm_admin_view(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    aid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        admin = await session.get(AdminUser, aid)
        if not admin: return
        perms = admin.all_perms()
    perm_text = "\n".join([f"  {'\u2705' if v else '\u274c'} {k}" for k, v in perms.items()])
    await cb.message.edit_text(
        f"🔑 <b>{admin.username or admin.telegram_id}</b>\n"
        f"🔢 ID: <code>{admin.telegram_id}</code>\n"
        f"🏷 نقش: {admin.role}\n\n"
        f"📋 دسترسی‌ها:\n{perm_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 حذف", callback_data=f"adm_del_admin_{aid}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_admins")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_del_admin_"))
async def adm_del_admin(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    aid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        admin = await session.get(AdminUser, aid)
        if admin: await session.delete(admin)
    await cb.answer("✅ ادمین حذف شد.", show_alert=True)


# ─ Settings ──────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️ فقط سوپرادمین.", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        s = await get_all_settings(session)
    await cb.message.edit_text(
        f"⚙️ <b>تنظیمات</b>\n\n"
        f"📈 Markup: <b>{s.get('smm_markup_percent','20')}%</b>\n"
        f"🟢 USDT: <code>{s.get('usdt_wallet','❌')[:20]}</code>\n"
        f"💸 TON: <code>{s.get('ton_wallet','❌')[:20]}</code>\n"
        f"⚡ TRX: <code>{s.get('trx_wallet','❌')[:20]}</code>\n"
        f"📞 پشتیبانی: @{s.get('support_username','❌')}\n"
        f"🤖 نام بات: {s.get('bot_name','SMM Panel')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 Markup",       callback_data="adm_set_smm_markup_percent")],
            [InlineKeyboardButton(text="🟢 USDT Wallet",  callback_data="adm_set_usdt_wallet")],
            [InlineKeyboardButton(text="💸 TON Wallet",   callback_data="adm_set_ton_wallet")],
            [InlineKeyboardButton(text="⚡ TRX Wallet",   callback_data="adm_set_trx_wallet")],
            [InlineKeyboardButton(text="📞 پشتیبانی",    callback_data="adm_set_support_username")],
            [InlineKeyboardButton(text="🤖 نام بات",       callback_data="adm_set_bot_name")],
            [InlineKeyboardButton(text="🔙 بازگشت",       callback_data="adm_menu")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_set_"))
async def adm_set_start(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    key = cb.data[8:]  # remove "adm_set_"
    labels = {
        "smm_markup_percent": "Markup % (مثال: 20)",
        "usdt_wallet":        "آدرس USDT (TRC20)",
        "ton_wallet":         "آدرس TON",
        "trx_wallet":         "آدرس TRX",
        "support_username":   "یوزرنیم پشتیبانی (بدون @)",
        "bot_name":           "نام بات",
    }
    label = labels.get(key, key)
    await state.set_state(AdminState.set_value)
    await state.update_data(setting_key=key)
    await cb.message.edit_text(f"⚙️ مقدار جدید <b>{label}</b> را وارد کنید:", parse_mode="HTML")


@router.message(AdminState.set_value)
async def adm_set_value(msg: Message, state: FSMContext):
    if not is_super(msg.from_user.id): return
    data = await state.get_data(); await state.clear()
    value = (msg.text or "").strip()
    async with AsyncSessionLocal() as session:
        await set_setting(session, data["setting_key"], value)
    await msg.answer(f"✅ تنظیم <b>{data['setting_key']}</b> ذخیره شد.", parse_mode="HTML")


# ─ Broadcast ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(cb: CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.broadcast_msg)
    await cb.message.edit_text("📢 متن پیام همگانی را بنویسید:")


@router.message(AdminState.broadcast_msg)
async def adm_broadcast_send(msg: Message, state: FSMContext):
    if not is_super(msg.from_user.id): return
    await state.clear()
    text = msg.text or ""
    async with AsyncSessionLocal() as session:
        users = await get_all_users(session)
    sent = failed = 0
    for user in users:
        try:
            await msg.bot.send_message(user.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
    await msg.answer(f"✅ ارسال شد: {sent} | شکست: {failed}")


# ─ Orders ───────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_orders")
async def adm_orders(cb: CallbackQuery):
    if not await check_admin_cb(cb, "manage_orders"): return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        orders = await get_all_orders(session)

    if not orders:
        await cb.message.edit_text(
            "📦 سفارشی ثبت نشده.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu")]
            ])
        )
        return

    si = {"pending": "⏳", "processing": "⏳", "completed": "✅", "cancelled": "❌"}
    lines = [f"{si.get(o.status,'🔵')} <b>#{o.id}</b> [{o.service_id}] ${float(o.sell_price):.2f}" for o in orders]
    await cb.message.edit_text(
        "📦 <b>آخرین سفارش‌ها</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu")]
        ]), parse_mode="HTML"
    )
