"""
Admin panel handler - full management.
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
from db.database import AsyncSessionLocal
from db.models import User, AdminUser, Transaction, Order, AdminSetting
from services.user_service import (
    get_user, get_setting, set_setting, get_admin,
    ban_user, unban_user, add_balance, get_all_users
)
from sqlalchemy import select, func

logger   = logging.getLogger("admin")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class AdminState(StatesGroup):
    add_admin_id     = State()
    add_admin_role   = State()
    ban_user_id      = State()
    unban_user_id    = State()
    credit_user_id   = State()
    credit_amount    = State()
    debit_user_id    = State()
    debit_amount     = State()
    set_markup       = State()
    set_wallet       = State()
    set_support      = State()
    set_bot_name     = State()
    broadcast_msg    = State()
    search_user      = State()


def is_superadmin(telegram_id: int) -> bool:
    return telegram_id == ADMIN_ID


async def check_admin(cb: CallbackQuery, perm: str = None) -> bool:
    if cb.from_user.id == ADMIN_ID:
        return True
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, cb.from_user.id)
        if not admin:
            await cb.answer("⛔️ \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f.", show_alert=True)
            return False
        if perm and not admin.has_perm(perm):
            await cb.answer(f"⛔️ \u062f\u0633\u062a\u0631\u0633\u06cc {perm} \u0646\u062f\u0627\u0631\u06cc\u062f.", show_alert=True)
            return False
    return True


# ─── Admin main menu ─────────────────────────────────────────────────────────────
def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 \u0622\u0645\u0627\u0631 \u06a9\u0644\u06cc",            callback_data="adm_stats")],
        [InlineKeyboardButton(text="👥 \u0645\u062f\u06cc\u0631\u06cc\u062a \u06a9\u0627\u0631\u0628\u0631\u0627\u0646",      callback_data="adm_users")],
        [InlineKeyboardButton(text="💰 \u0648\u0627\u0631\u06cc\u0632\u06cc\u200c\u0647\u0627\u06cc \u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631",   callback_data="adm_pending_deps")],
        [InlineKeyboardButton(text="📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627",             callback_data="adm_orders")],
        [InlineKeyboardButton(text="🔑 \u0645\u062f\u06cc\u0631\u06cc\u062a \u0627\u062f\u0645\u06cc\u0646\u200c\u0647\u0627",     callback_data="adm_admins")],
        [InlineKeyboardButton(text="⚙️ \u062a\u0646\u0638\u06cc\u0645\u0627\u062a",             callback_data="adm_settings")],
        [InlineKeyboardButton(text="📢 \u067e\u062e\u0634 \u0647\u0645\u06af\u0627\u0646\u06cc",          callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a",               callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_admin")
async def adm_entry(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb): return
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🔑 <b>\u067e\u0646\u0644 \u0645\u062f\u06cc\u0631\u06cc\u062a</b>\n\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=admin_main_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_menu")
async def adm_menu_back(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb): return
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🔑 <b>\u067e\u0646\u0644 \u0645\u062f\u06cc\u0631\u06cc\u062a</b>\n\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=admin_main_kb(), parse_mode="HTML"
    )


# ─── Stats ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    if not await check_admin(cb, "view_stats"): return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        total_users   = (await session.execute(select(func.count(User.id)))).scalar()
        banned_users  = (await session.execute(select(func.count(User.id)).where(User.is_banned == True))).scalar()
        total_orders  = (await session.execute(select(func.count(Order.id)))).scalar()
        pending_deps  = (await session.execute(
            select(func.count(Transaction.id)).where(Transaction.type == "deposit", Transaction.status == "pending")
        )).scalar()
        total_revenue = (await session.execute(
            select(func.sum(Transaction.amount)).where(Transaction.type == "deposit", Transaction.status == "approved")
        )).scalar() or 0
        markup = await get_setting(session, "smm_markup_percent", "20")

    await cb.message.edit_text(
        "📊 <b>\u0622\u0645\u0627\u0631 \u06a9\u0644\u06cc</b>\n\n"
        f"👥 \u06a9\u0627\u0631\u0628\u0631\u0627\u0646: <b>{total_users}</b> (\u0645\u0633\u062f\u0648\u062f: {banned_users})\n"
        f"📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627: <b>{total_orders}</b>\n"
        f"⏳ \u0648\u0627\u0631\u06cc\u0632\u06cc \u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631: <b>{pending_deps}</b>\n"
        f"💰 \u06a9\u0644 \u0648\u0627\u0631\u06cc\u0632\u06cc: <b>${float(total_revenue):.2f}</b>\n"
        f"📈 Markup: <b>{markup}%</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_menu")]
        ]), parse_mode="HTML"
    )


# ─── Pending deposits ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_pending_deps")
async def adm_pending_deps(cb: CallbackQuery):
    if not await check_admin(cb, "manage_deposits"): return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(Transaction).where(
                Transaction.type == "deposit",
                Transaction.status == "pending"
            ).order_by(Transaction.created_at.asc()).limit(10)
        )
        txs = r.scalars().all()
        if not txs:
            await cb.message.edit_text(
                "✅ \u0647\u06cc\u0686 \u0648\u0627\u0631\u06cc\u0632\u06cc \u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631 \u0646\u06cc\u0633\u062a.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_menu")]
                ]), parse_mode="HTML"
            ); return

        rows = []
        for tx in txs:
            user = await session.get(User, tx.user_id)
            uname = user.display_name() if user else f"ID:{tx.user_id}"
            rows.append([InlineKeyboardButton(
                text=f"${float(tx.amount):.2f} | {tx.method} | {uname[:15]}",
                callback_data=f"adm_dep_view_{tx.id}"
            )])
        rows.append([InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_menu")])

    await cb.message.edit_text(
        f"⏳ <b>\u0648\u0627\u0631\u06cc\u0632\u06cc\u200c\u0647\u0627\u06cc \u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631 ({len(txs)})</b>\n\u0631\u0648\u06cc \u0647\u0631 \u06a9\u062f\u0627\u0645 \u0628\u0632\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_view_"))
async def adm_dep_view(cb: CallbackQuery):
    if not await check_admin(cb, "manage_deposits"): return
    await cb.answer()
    tx_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        tx   = await session.get(Transaction, tx_id)
        if not tx: return
        user = await session.get(User, tx.user_id)
        uname = user.display_name() if user else f"ID:{tx.user_id}"

    await cb.message.edit_text(
        f"💰 <b>\u0648\u0627\u0631\u06cc\u0632 #{tx_id}</b>\n\n"
        f"👤 \u06a9\u0627\u0631\u0628\u0631: {uname} (@{user.username or '-'})\n"
        f"💵 \u0645\u0628\u0644\u063a: <b>${float(tx.amount):.4f}</b>\n"
        f"💳 \u0631\u0648\u0634: {tx.method}\n"
        f"🔗 Hash: <code>{tx.tx_hash}</code>\n"
        f"📅 \u062a\u0627\u0631\u06cc\u062e: {tx.created_at.strftime('%Y-%m-%d %H:%M')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ \u062a\u0627\u06cc\u06cc\u062f", callback_data=f"adm_dep_ok_{tx_id}"),
             InlineKeyboardButton(text="❌ \u0631\u062f",    callback_data=f"adm_dep_no_{tx_id}")],
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_pending_deps")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_ok_"))
async def adm_dep_approve(cb: CallbackQuery):
    if not await check_admin(cb, "manage_deposits"): return
    await cb.answer()
    tx_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        tx = await session.get(Transaction, tx_id)
        if not tx or tx.status != "pending":
            await cb.answer("❌ \u0642\u0628\u0644\u0627\u064b \u067e\u0631\u062f\u0627\u0632\u0634 \u0634\u062f\u0647.", show_alert=True); return
        tx.status = "approved"
        await add_balance(session, tx.user_id, float(tx.amount))
        user = await session.get(User, tx.user_id)
        await session.commit()

    await cb.message.edit_text(
        f"✅ <b>\u0648\u0627\u0631\u06cc\u0632 #{tx_id} \u062a\u0627\u06cc\u06cc\u062f \u0634\u062f.</b>\n"
        f"💰 ${float(tx.amount):.4f} \u0628\u0647 \u062d\u0633\u0627\u0628 \u06a9\u0627\u0631\u0628\u0631 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f.",
        parse_mode="HTML"
    )
    # Notify user
    try:
        await cb.bot.send_message(
            user.telegram_id,
            f"✅ <b>\u0648\u0627\u0631\u06cc\u0632 \u062a\u0627\u06cc\u06cc\u062f \u0634\u062f!</b>\n"
            f"💰 ${float(tx.amount):.4f} \u0628\u0647 \u062d\u0633\u0627\u0628\u062a\u0627\u0646 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_dep_no_"))
async def adm_dep_reject(cb: CallbackQuery):
    if not await check_admin(cb, "manage_deposits"): return
    await cb.answer()
    tx_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        tx = await session.get(Transaction, tx_id)
        if not tx or tx.status != "pending":
            await cb.answer("❌ \u0642\u0628\u0644\u0627\u064b \u067e\u0631\u062f\u0627\u0632\u0634 \u0634\u062f\u0647.", show_alert=True); return
        tx.status = "rejected"
        user = await session.get(User, tx.user_id)
        await session.commit()

    await cb.message.edit_text(
        f"❌ <b>\u0648\u0627\u0631\u06cc\u0632 #{tx_id} \u0631\u062f \u0634\u062f.</b>",
        parse_mode="HTML"
    )
    try:
        await cb.bot.send_message(
            user.telegram_id,
            f"❌ <b>\u0648\u0627\u0631\u06cc\u0632 \u0634\u0645\u0627 \u0631\u062f \u0634\u062f.</b>\n"
            "\u0644\u0637\u0641\u0627\u064b \u0628\u0627 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc \u062a\u0645\u0627\u0633 \u0628\u06af\u06cc\u0631\u06cc\u062f.",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ─── User management ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_users")
async def adm_users(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb, "manage_users"): return
    await cb.answer()
    await cb.message.edit_text(
        "👥 <b>\u0645\u062f\u06cc\u0631\u06cc\u062a \u06a9\u0627\u0631\u0628\u0631\u0627\u0646</b>\n\u06cc\u06a9 \u0639\u0645\u0644\u06cc\u0627\u062a \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 \u062c\u0633\u062a\u062c\u0648 \u06a9\u0627\u0631\u0628\u0631",      callback_data="adm_search_user")],
            [InlineKeyboardButton(text="🚫 \u0628\u0646 \u06a9\u0627\u0631\u0628\u0631",          callback_data="adm_ban_user")],
            [InlineKeyboardButton(text="✅ \u0627\u0646\u0628\u0646 \u06a9\u0627\u0631\u0628\u0631",         callback_data="adm_unban_user")],
            [InlineKeyboardButton(text="💸 \u0634\u0627\u0631\u0698 \u062f\u0633\u062a\u06cc",         callback_data="adm_credit_user")],
            [InlineKeyboardButton(text="💸 \u06a9\u0633\u0631 \u0645\u0648\u062c\u0648\u062f\u06cc",       callback_data="adm_debit_user")],
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a",               callback_data="adm_menu")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_search_user")
async def adm_search_user_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb, "manage_users"): return
    await cb.answer()
    await state.set_state(AdminState.search_user)
    await cb.message.edit_text(
        "🔍 \u0634\u0646\u0627\u0633\u0647 \u062a\u0644\u06af\u0631\u0627\u0645 \u06cc\u0627 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u06a9\u0627\u0631\u0628\u0631 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML"
    )


@router.message(AdminState.search_user)
async def adm_search_user_handle(msg: Message, state: FSMContext):
    if not await _check_admin_msg(msg): return
    await state.clear()
    q = (msg.text or "").strip()
    async with AsyncSessionLocal() as session:
        try:
            tg_id = int(q)
            r = await session.execute(select(User).where(User.telegram_id == tg_id))
        except ValueError:
            r = await session.execute(select(User).where(User.username.ilike(f"%{q}%")))
        users = r.scalars().all()

    if not users:
        await msg.answer("❌ \u06a9\u0627\u0631\u0628\u0631\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f."); return

    rows = []
    for u in users[:10]:
        ban_icon = "🚫" if u.is_banned else "✅"
        rows.append([InlineKeyboardButton(
            text=f"{ban_icon} {u.display_name()} | ${float(u.balance):.2f}",
            callback_data=f"adm_user_view_{u.id}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_users")])
    await msg.answer(
        f"🔍 {len(users)} \u06a9\u0627\u0631\u0628\u0631 \u06cc\u0627\u0641\u062a \u0634\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_user_view_"))
async def adm_user_view(cb: CallbackQuery):
    if not await check_admin(cb, "manage_users"): return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        user = await session.get(User, uid)
        if not user: return
        order_count = (await session.execute(
            select(func.count(Order.id)).where(Order.user_id == uid)
        )).scalar()

    ban_status = "🚫 \u0645\u0633\u062f\u0648\u062f" if user.is_banned else "✅ \u0641\u0639\u0627\u0644"
    phone = user.phone or "❌"
    await cb.message.edit_text(
        f"👤 <b>{user.display_name()}</b>\n\n"
        f"📎 @{user.username or '-'}\n"
        f"🔢 ID: <code>{user.telegram_id}</code>\n"
        f"📞 \u0634\u0645\u0627\u0631\u0647: {phone}\n"
        f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${float(user.balance):.4f}</b>\n"
        f"📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627: {order_count}\n"
        f"📅 \u0639\u0636\u0648\u06cc\u062a: {user.created_at.strftime('%Y-%m-%d')}\n"
        f"🔴 \u0648\u0636\u0639\u06cc\u062a: {ban_status}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 \u0628\u0646",  callback_data=f"adm_do_ban_{user.telegram_id}"),
             InlineKeyboardButton(text="✅ \u0627\u0646\u0628\u0646", callback_data=f"adm_do_unban_{user.telegram_id}")],
            [InlineKeyboardButton(text="💸 \u0634\u0627\u0631\u0698", callback_data=f"adm_do_credit_{uid}"),
             InlineKeyboardButton(text="💸 \u06a9\u0633\u0631",  callback_data=f"adm_do_debit_{uid}")],
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_users")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_do_ban_"))
async def adm_do_ban(cb: CallbackQuery):
    if not await check_admin(cb, "manage_users"): return
    tg_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await ban_user(session, tg_id)
        await session.commit()
    await cb.answer("🚫 \u06a9\u0627\u0631\u0628\u0631 \u0628\u0646 \u0634\u062f.", show_alert=True)


@router.callback_query(F.data.startswith("adm_do_unban_"))
async def adm_do_unban(cb: CallbackQuery):
    if not await check_admin(cb, "manage_users"): return
    tg_id = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await unban_user(session, tg_id)
        await session.commit()
    await cb.answer("✅ \u06a9\u0627\u0631\u0628\u0631 \u0627\u0646\u0628\u0646 \u0634\u062f.", show_alert=True)


@router.callback_query(F.data.startswith("adm_do_credit_"))
async def adm_do_credit_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb, "manage_users"): return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    await state.set_state(AdminState.credit_amount)
    await state.update_data(target_uid=uid)
    await cb.message.edit_text(f"💸 \u0645\u0628\u0644\u063a \u0634\u0627\u0631\u0698 (\u062f\u0644\u0627\u0631) \u0628\u0631\u0627\u06cc \u06a9\u0627\u0631\u0628\u0631 #{uid}:", parse_mode="HTML")


@router.message(AdminState.credit_amount)
async def adm_credit_amount(msg: Message, state: FSMContext):
    if not await _check_admin_msg(msg): return
    try: amount = float(msg.text.strip())
    except: await msg.answer("❌ \u0639\u062f\u062f \u0635\u062d\u06cc\u062d."); return
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as session:
        user = await session.get(User, data["target_uid"])
        await add_balance(session, data["target_uid"], amount)
        from db.models import Transaction as Tx
        session.add(Tx(
            user_id=data["target_uid"], type="manual_credit",
            amount=amount, status="approved",
            description=f"Manual credit by admin"
        ))
        await session.commit()
    await msg.answer(f"✅ ${amount} \u0628\u0647 \u062d\u0633\u0627\u0628 \u06a9\u0627\u0631\u0628\u0631 \u0627\u0636\u0627\u0641\u0647 \u0634\u062f.")
    try:
        await msg.bot.send_message(user.telegram_id, f"✅ \u0645\u0648\u062c\u0648\u062f\u06cc \u0634\u0645\u0627 ${amount} \u0634\u0627\u0631\u0698 \u0634\u062f.")
    except Exception: pass


@router.callback_query(F.data.startswith("adm_do_debit_"))
async def adm_do_debit_start(cb: CallbackQuery, state: FSMContext):
    if not await check_admin(cb, "manage_users"): return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    await state.set_state(AdminState.debit_amount)
    await state.update_data(target_uid=uid)
    await cb.message.edit_text(f"💸 \u0645\u0628\u0644\u063a \u06a9\u0633\u0631 (\u062f\u0644\u0627\u0631) \u0628\u0631\u0627\u06cc \u06a9\u0627\u0631\u0628\u0631 #{uid}:", parse_mode="HTML")


@router.message(AdminState.debit_amount)
async def adm_debit_amount(msg: Message, state: FSMContext):
    if not await _check_admin_msg(msg): return
    try: amount = float(msg.text.strip())
    except: await msg.answer("❌ \u0639\u062f\u062f \u0635\u062d\u06cc\u062d."); return
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as session:
        from services.user_service import deduct_balance
        ok = await deduct_balance(session, data["target_uid"], amount)
        if not ok:
            await msg.answer("❌ \u0645\u0648\u062c\u0648\u062f\u06cc \u06a9\u0627\u0641\u06cc \u0646\u06cc\u0633\u062a."); return
        from db.models import Transaction as Tx
        session.add(Tx(
            user_id=data["target_uid"], type="manual_debit",
            amount=-amount, status="approved",
            description="Manual debit by admin"
        ))
        await session.commit()
    await msg.answer(f"✅ ${amount} \u0627\u0632 \u062d\u0633\u0627\u0628 \u06a9\u0627\u0631\u0628\u0631 \u06a9\u0633\u0631 \u0634\u062f.")


# ─── Admin management ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_admins")
async def adm_admins(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️ \u0641\u0642\u0637 \u0633\u0648\u067e\u0631\u0627\u062f\u0645\u06cc\u0646.", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        r = await session.execute(select(AdminUser).order_by(AdminUser.created_at.desc()))
        admins = r.scalars().all()

    rows = []
    for a in admins:
        rows.append([InlineKeyboardButton(
            text=f"🔑 {a.username or a.telegram_id} | {a.role}",
            callback_data=f"adm_admin_view_{a.id}"
        )])
    rows.append([InlineKeyboardButton(text="➕ \u0627\u0636\u0627\u0641\u0647 \u0627\u062f\u0645\u06cc\u0646", callback_data="adm_add_admin")])
    rows.append([InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_menu")])
    await cb.message.edit_text(
        f"🔑 <b>\u0627\u062f\u0645\u06cc\u0646\u200c\u0647\u0627 ({len(admins)})</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin_start(cb: CallbackQuery, state: FSMContext):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.add_admin_id)
    await cb.message.edit_text(
        "➕ <b>\u0627\u0636\u0627\u0641\u0647 \u0627\u062f\u0645\u06cc\u0646 \u062c\u062f\u06cc\u062f</b>\n\n"
        "\u0634\u0646\u0627\u0633\u0647 \u062a\u0644\u06af\u0631\u0627\u0645 \u0627\u062f\u0645\u06cc\u0646 \u062c\u062f\u06cc\u062f \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML"
    )


@router.message(AdminState.add_admin_id)
async def adm_add_admin_id(msg: Message, state: FSMContext):
    if not is_superadmin(msg.from_user.id): return
    try: tg_id = int(msg.text.strip())
    except: await msg.answer("❌ \u0634\u0646\u0627\u0633\u0647 \u0639\u062f\u062f\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.update_data(new_admin_id=tg_id)
    await state.set_state(AdminState.add_admin_role)
    await msg.answer(
        "\u0646\u0642\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 admin",     callback_data="adm_role_admin")],
            [InlineKeyboardButton(text="🛡 moderator", callback_data="adm_role_moderator")],
            [InlineKeyboardButton(text="📞 support",   callback_data="adm_role_support")],
        ])
    )


@router.callback_query(F.data.startswith("adm_role_"))
async def adm_add_admin_role(cb: CallbackQuery, state: FSMContext):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    role = cb.data[9:]  # admin, moderator, support
    data = await state.get_data()
    await state.clear()
    tg_id = data.get("new_admin_id")

    # Default permissions by role
    perms = {
        "admin":     {"manage_users": True, "manage_orders": True, "manage_deposits": True, "view_stats": True},
        "moderator": {"manage_users": True, "manage_orders": True, "manage_deposits": False, "view_stats": True},
        "support":   {"manage_users": False, "manage_orders": False, "manage_deposits": False, "view_stats": True},
    }.get(role, {})

    async with AsyncSessionLocal() as session:
        existing = await session.execute(select(AdminUser).where(AdminUser.telegram_id == tg_id))
        if existing.scalar_one_or_none():
            await cb.message.edit_text("❌ \u0627\u06cc\u0646 \u06a9\u0627\u0631\u0628\u0631 \u0642\u0628\u0644\u0627\u064b \u0627\u062f\u0645\u06cc\u0646 \u0627\u0633\u062a."); return
        session.add(AdminUser(
            telegram_id=tg_id, role=role,
            permissions=json.dumps(perms)
        ))
        await session.commit()

    await cb.message.edit_text(
        f"✅ \u0627\u062f\u0645\u06cc\u0646 \u062c\u062f\u06cc\u062f \u0628\u0627 \u0646\u0642\u0634 <b>{role}</b> \u0627\u0636\u0627\u0641\u0647 \u0634\u062f.\n"
        f"🔢 ID: <code>{tg_id}</code>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_admin_view_"))
async def adm_admin_view(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
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
        f"🏷 \u0646\u0642\u0634: {admin.role}\n\n"
        f"📋 \u062f\u0633\u062a\u0631\u0633\u06cc\u200c\u0647\u0627:\n{perm_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 \u062d\u0630\u0641 \u0627\u062f\u0645\u06cc\u0646", callback_data=f"adm_del_admin_{aid}")],
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_admins")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_del_admin_"))
async def adm_del_admin(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    aid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        admin = await session.get(AdminUser, aid)
        if admin:
            await session.delete(admin)
            await session.commit()
    await cb.answer("✅ \u0627\u062f\u0645\u06cc\u0646 \u062d\u0630\u0641 \u0634\u062f.", show_alert=True)
    await adm_admins(cb)


# ─── Settings ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        markup   = await get_setting(session, "smm_markup_percent", "20")
        usdt_trc = await get_setting(session, "usdt_trc20_wallet", "❌")
        usdt_erc = await get_setting(session, "usdt_erc20_wallet", "❌")
        ton      = await get_setting(session, "ton_wallet", "❌")
        trx      = await get_setting(session, "trx_wallet", "❌")
        support  = await get_setting(session, "support_username", "❌")
        bot_name = await get_setting(session, "bot_name", "SMM Panel")

    await cb.message.edit_text(
        f"⚙️ <b>\u062a\u0646\u0638\u06cc\u0645\u0627\u062a</b>\n\n"
        f"📈 Markup: <b>{markup}%</b>\n"
        f"🟢 USDT TRC20: <code>{usdt_trc[:20] if usdt_trc else '\u274c'}</code>\n"
        f"🔵 USDT ERC20: <code>{usdt_erc[:20] if usdt_erc else '\u274c'}</code>\n"
        f"💸 TON: <code>{ton[:20] if ton else '\u274c'}</code>\n"
        f"🔴 TRX: <code>{trx[:20] if trx else '\u274c'}</code>\n"
        f"📞 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc: @{support}\n"
        f"🤖 \u0646\u0627\u0645 \u0628\u0627\u062a: {bot_name}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 \u062a\u063a\u06cc\u06cc\u0631 Markup",       callback_data="adm_set_markup")],
            [InlineKeyboardButton(text="🟢 USDT TRC20",          callback_data="adm_set_usdt_trc20")],
            [InlineKeyboardButton(text="🔵 USDT ERC20",          callback_data="adm_set_usdt_erc20")],
            [InlineKeyboardButton(text="💸 TON Wallet",          callback_data="adm_set_ton")],
            [InlineKeyboardButton(text="🔴 TRX Wallet",          callback_data="adm_set_trx")],
            [InlineKeyboardButton(text="📞 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc",          callback_data="adm_set_support")],
            [InlineKeyboardButton(text="🤖 \u0646\u0627\u0645 \u0628\u0627\u062a",             callback_data="adm_set_botname")],
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a",               callback_data="adm_menu")],
        ]), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_set_"))
async def adm_set_start(cb: CallbackQuery, state: FSMContext):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    key_map = {
        "adm_set_markup":      ("smm_markup_percent", "Markup % (\u0645\u062b\u0627\u0644: 20)"),
        "adm_set_usdt_trc20":  ("usdt_trc20_wallet",  "\u0622\u062f\u0631\u0633 USDT TRC20"),
        "adm_set_usdt_erc20":  ("usdt_erc20_wallet",  "\u0622\u062f\u0631\u0633 USDT ERC20"),
        "adm_set_ton":         ("ton_wallet",          "\u0622\u062f\u0631\u0633 TON"),
        "adm_set_trx":         ("trx_wallet",          "\u0622\u062f\u0631\u0633 TRX"),
        "adm_set_support":     ("support_username",    "\u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc (\u0628\u062f\u0648\u0646 @)"),
        "adm_set_botname":     ("bot_name",            "\u0646\u0627\u0645 \u0628\u0627\u062a"),
    }
    if cb.data not in key_map: return
    setting_key, prompt = key_map[cb.data]
    await state.set_state(AdminState.set_wallet)
    await state.update_data(setting_key=setting_key)
    await cb.message.edit_text(f"⚙️ {prompt} \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:", parse_mode="HTML")


@router.message(AdminState.set_wallet)
async def adm_set_value(msg: Message, state: FSMContext):
    if not is_superadmin(msg.from_user.id): return
    data = await state.get_data()
    await state.clear()
    value = (msg.text or "").strip()
    async with AsyncSessionLocal() as session:
        await set_setting(session, data["setting_key"], value)
        await session.commit()
    await msg.answer(f"✅ \u062a\u0646\u0638\u06cc\u0645 <b>{data['setting_key']}</b> \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f.", parse_mode="HTML")


# ─── Broadcast ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_superadmin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.broadcast_msg)
    await cb.message.edit_text(
        "📢 <b>\u067e\u062e\u0634 \u0647\u0645\u06af\u0627\u0646\u06cc</b>\n\n"
        "\u0645\u062a\u0646 \u067e\u06cc\u0627\u0645 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:",
        parse_mode="HTML"
    )


@router.message(AdminState.broadcast_msg)
async def adm_broadcast_send(msg: Message, state: FSMContext):
    if not is_superadmin(msg.from_user.id): return
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

    await msg.answer(f"✅ \u0627\u0631\u0633\u0627\u0644 \u0634\u062f: {sent} | \u0634\u06a9\u0633\u062a: {failed}")


# ─── Orders list ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_orders")
async def adm_orders(cb: CallbackQuery):
    if not await check_admin(cb, "manage_orders"): return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        r = await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(15)
        )
        orders = r.scalars().all()

    if not orders:
        await cb.message.edit_text(
            "📦 \u0633\u0641\u0627\u0631\u0634\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_menu")]
            ]), parse_mode="HTML"
        ); return

    status_icons = {"pending": "⏳", "processing": "🔄", "completed": "✅", "cancelled": "❌"}
    lines = []
    for o in orders:
        icon = status_icons.get(o.status, "🟡")
        lines.append(f"{icon} <b>#{o.id}</b> [{o.service_id}] ${float(o.charge):.4f}")

    await cb.message.edit_text(
        "📦 <b>\u0622\u062e\u0631\u06cc\u0646 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_menu")]
        ]), parse_mode="HTML"
    )


# Helper
async def _check_admin_msg(msg: Message) -> bool:
    if msg.from_user.id == ADMIN_ID: return True
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, msg.from_user.id)
        return admin is not None
