"""
User panel handler - profile, balance, orders, deposit, SMM services.
"""
import os
import logging
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User, Transaction
from services.user_service import get_user, get_setting, add_balance
from services.order_service import get_user_orders, get_markup, apply_markup
from sqlalchemy import select

logger   = logging.getLogger("user")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class UserState(StatesGroup):
    verify_phone    = State()
    deposit_amount  = State()
    deposit_hash    = State()
    order_link      = State()
    order_qty       = State()
    order_extra     = State()


# ─── Main user menu ────────────────────────────────────────────────────────────────
def user_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 \u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u0645\u0646",         callback_data="u_profile")],
        [InlineKeyboardButton(text="💰 \u0634\u0627\u0631\u0698 \u062d\u0633\u0627\u0628",          callback_data="u_deposit")],
        [InlineKeyboardButton(text="📊 \u062e\u062f\u0645\u0627\u062a SMM",            callback_data="u_smm_cats_0")],
        [InlineKeyboardButton(text="📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627\u06cc \u0645\u0646",        callback_data="u_my_orders")],
        [InlineKeyboardButton(text="🔍 \u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u062e\u062f\u0645\u0627\u062a",      callback_data="u_smm_search")],
        [InlineKeyboardButton(text="📞 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc",             callback_data="u_support")],
    ])


@router.message(F.text == "/start")
async def user_start(msg: Message, state: FSMContext):
    await state.clear()
    db_user: User = msg.bot.get("db_user_cache", {}).get(msg.from_user.id)
    async with AsyncSessionLocal() as session:
        user = await get_user(session, msg.from_user.id)
        if not user:
            from services.user_service import get_or_create_user
            user = await get_or_create_user(session, msg.from_user)
            await session.commit()
        bot_name = await get_setting(session, "bot_name", "SMM Panel")
        bal = float(user.balance)
        phone_status = f"✅ {user.phone}" if user.phone else "❌ \u0648\u0631\u06cc\u0641\u0627\u06cc \u0646\u0634\u062f\u0647"

    await msg.answer(
        f"🚀 <b>\u062e\u0648\u0634 \u0622\u0645\u062f\u06cc\u062f \u0628\u0647 {bot_name}</b>\n\n"
        f"👤 {user.display_name()}\n"
        f"📞 \u0634\u0645\u0627\u0631\u0647: {phone_status}\n"
        f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal:.4f}</b>\n\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=user_main_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "u_menu")
async def u_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    async with AsyncSessionLocal() as session:
        user = await get_user(session, cb.from_user.id)
        bot_name = await get_setting(session, "bot_name", "SMM Panel")
        bal = float(user.balance) if user else 0
        phone_status = f"✅ {user.phone}" if (user and user.phone) else "❌ \u0648\u0631\u06cc\u0641\u0627\u06cc \u0646\u0634\u062f\u0647"
    await cb.message.edit_text(
        f"🚀 <b>{bot_name}</b>\n\n"
        f"📞 \u0634\u0645\u0627\u0631\u0647: {phone_status}\n"
        f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal:.4f}</b>\n\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=user_main_kb(), parse_mode="HTML"
    )


# ─── Profile ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "u_profile")
async def u_profile(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        user = await get_user(session, cb.from_user.id)
        if not user: return
        r = await session.execute(
            select(Transaction).where(Transaction.user_id == user.id, Transaction.status == "approved")
        )
        txs = r.scalars().all()
        total_deposit = sum(float(t.amount) for t in txs if t.type == "deposit")
        total_spent   = abs(sum(float(t.amount) for t in txs if t.type == "order"))
        phone_status  = f"✅ <code>{user.phone}</code>" if user.phone else "❌ \u0648\u0631\u06cc\u0641\u0627\u06cc \u0646\u0634\u062f\u0647"

    text = (
        f"👤 <b>\u067e\u0631\u0648\u0641\u0627\u06cc\u0644 \u0634\u0645\u0627</b>\n\n"
        f"🔵 \u0646\u0627\u0645: <b>{user.display_name()}</b>\n"
        f"📎 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645: @{user.username or '-'}\n"
        f"📞 \u0634\u0645\u0627\u0631\u0647: {phone_status}\n"
        f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${float(user.balance):.4f}</b>\n"
        f"📅 \u0639\u0636\u0648\u06cc\u062a \u0627\u0632: <b>{user.created_at.strftime('%Y-%m-%d')}</b>\n\n"
        f"📊 \u06a9\u0644 \u0634\u0627\u0631\u0698: <b>${total_deposit:.2f}</b>\n"
        f"📦 \u06a9\u0644 \u062e\u0631\u062c: <b>${total_spent:.2f}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📞 \u0648\u0631\u06cc\u0641\u0627\u06cc \u0634\u0645\u0627\u0631\u0647", callback_data="u_verify_phone")],
        [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")],
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ─── Phone verification ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "u_verify_phone")
async def u_verify_phone_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(UserState.verify_phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 \u0627\u0631\u0633\u0627\u0644 \u0634\u0645\u0627\u0631\u0647", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await cb.message.answer(
        "📞 <b>\u0648\u0631\u06cc\u0641\u0627\u06cc \u0634\u0645\u0627\u0631\u0647</b>\n\n"
        "\u062f\u06a9\u0645\u0647 \u0632\u06cc\u0631 \u0631\u0627 \u0628\u0632\u0646\u06cc\u062f \u062a\u0627 \u0634\u0645\u0627\u0631\u0647\u062a\u0627\u0646 \u0648\u0631\u06cc\u0641\u0627\u06cc \u0634\u0648\u062f:",
        reply_markup=kb, parse_mode="HTML"
    )


@router.message(UserState.verify_phone, F.contact)
async def u_verify_phone_done(msg: Message, state: FSMContext):
    await state.clear()
    phone = msg.contact.phone_number
    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        from db.models import User as UserModel
        await session.execute(
            update(UserModel).where(UserModel.telegram_id == msg.from_user.id)
            .values(phone=phone)
        )
        await session.commit()
    await msg.answer(
        f"✅ \u0634\u0645\u0627\u0631\u0647 <code>{phone}</code> \u0648\u0631\u06cc\u0641\u0627\u06cc \u0634\u062f!",
        reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
    )
    await msg.answer("\u0628\u0647 \u0645\u0646\u0648 \u0628\u0631\u06af\u0634\u062a\u06cc\u062f:", reply_markup=user_main_kb())


# ─── Deposit ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "u_deposit")
async def u_deposit_menu(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        usdt_trc = await get_setting(session, "usdt_trc20_wallet", "")
        usdt_erc = await get_setting(session, "usdt_erc20_wallet", "")
        ton      = await get_setting(session, "ton_wallet", "")
        trx      = await get_setting(session, "trx_wallet", "")
        min_dep  = await get_setting(session, "min_deposit", "1")

    rows = []
    if usdt_trc: rows.append([InlineKeyboardButton(text="🟢 USDT TRC20", callback_data="u_dep_usdt_trc20")])
    if usdt_erc: rows.append([InlineKeyboardButton(text="🔵 USDT ERC20", callback_data="u_dep_usdt_erc20")])
    if ton:      rows.append([InlineKeyboardButton(text="💸 TON",        callback_data="u_dep_ton")])
    if trx:      rows.append([InlineKeyboardButton(text="🔴 TRX",        callback_data="u_dep_trx")])
    rows.append([InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")])

    await cb.message.edit_text(
        f"💰 <b>\u0634\u0627\u0631\u0698 \u062d\u0633\u0627\u0628</b>\n\n"
        f"ℹ\ufe0f \u062d\u062f\u0627\u0642\u0644 \u0648\u0627\u0631\u06cc\u0632: <b>${min_dep}</b>\n\n"
        "\u0631\u0648\u0634 \u067e\u0631\u062f\u0627\u062e\u062a \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("u_dep_"))
async def u_dep_method(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    method = cb.data[6:]  # usdt_trc20, usdt_erc20, ton, trx
    method_map = {
        "usdt_trc20": ("usdt_trc20_wallet", "USDT TRC20", "🟢"),
        "usdt_erc20": ("usdt_erc20_wallet", "USDT ERC20", "🔵"),
        "ton":        ("ton_wallet",         "TON",        "💸"),
        "trx":        ("trx_wallet",         "TRX",        "🔴"),
    }
    if method not in method_map: return
    setting_key, label, icon = method_map[method]

    async with AsyncSessionLocal() as session:
        wallet = await get_setting(session, setting_key, "")
        min_dep = await get_setting(session, "min_deposit", "1")
        max_dep = await get_setting(session, "max_deposit", "1000")

    await state.set_state(UserState.deposit_amount)
    await state.update_data(dep_method=method, dep_wallet=wallet, dep_label=label)
    await cb.message.edit_text(
        f"{icon} <b>\u0634\u0627\u0631\u0698 \u0628\u0627 {label}</b>\n\n"
        f"💳 \u0622\u062f\u0631\u0633 \u06a9\u06cc\u0641 \u067e\u0648\u0644:\n<code>{wallet}</code>\n\n"
        f"ℹ\ufe0f \u062d\u062f\u0627\u0642\u0644: <b>${min_dep}</b> | \u062d\u062f\u0627\u06a9\u062b\u0631: <b>${max_dep}</b>\n\n"
        "\u0645\u0628\u0644\u063a \u0648\u0627\u0631\u06cc\u0632 (\u062f\u0644\u0627\u0631) \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_amount)
async def u_dep_amount(msg: Message, state: FSMContext):
    try:
        amount = float(msg.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ \u0645\u0628\u0644\u063a \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return

    async with AsyncSessionLocal() as session:
        min_dep = float(await get_setting(session, "min_deposit", "1"))
        max_dep = float(await get_setting(session, "max_deposit", "1000"))
    if amount < min_dep or amount > max_dep:
        await msg.answer(f"❌ \u0645\u0628\u0644\u063a \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 ${min_dep} \u0648 ${max_dep} \u0628\u0627\u0634\u062f."); return

    await state.update_data(dep_amount=amount)
    await state.set_state(UserState.deposit_hash)
    await msg.answer(
        f"✅ \u0645\u0628\u0644\u063a: <b>${amount}</b>\n\n"
        "🔗 \u0627\u06a9\u0646\u0648\u0646 \u062a\u0631\u0627\u06a9\u0646\u0634\u0646 \u0647\u0634 (TX Hash) \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML"
    )


@router.message(UserState.deposit_hash)
async def u_dep_hash(msg: Message, state: FSMContext):
    tx_hash = (msg.text or "").strip()
    if len(tx_hash) < 10:
        await msg.answer("❌ \u0647\u0634 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return

    data = await state.get_data()
    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await get_user(session, msg.from_user.id)
        if not user: return
        from db.models import Transaction as Tx
        tx = Tx(
            user_id=user.id,
            type="deposit",
            amount=data["dep_amount"],
            status="pending",
            method=data["dep_method"],
            tx_hash=tx_hash,
            wallet_address=data["dep_wallet"],
            description=f"Deposit {data['dep_label']} ${data['dep_amount']}"
        )
        session.add(tx)
        await session.commit()
        tx_id = tx.id

    # Notify admins
    try:
        await msg.bot.send_message(
            ADMIN_ID,
            f"💰 <b>\u0648\u0627\u0631\u06cc\u0632 \u062c\u062f\u06cc\u062f</b>\n\n"
            f"👤 \u06a9\u0627\u0631\u0628\u0631: {user.display_name()} (@{user.username or '-'})\n"
            f"💵 \u0645\u0628\u0644\u063a: <b>${data['dep_amount']}</b>\n"
            f"💳 \u0631\u0648\u0634: {data['dep_label']}\n"
            f"🔗 Hash: <code>{tx_hash}</code>\n"
            f"🔢 TX ID: <code>{tx_id}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ \u062a\u0627\u06cc\u06cc\u062f", callback_data=f"adm_dep_ok_{tx_id}"),
                 InlineKeyboardButton(text="❌ \u0631\u062f",    callback_data=f"adm_dep_no_{tx_id}")]
            ]),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await msg.answer(
        f"✅ <b>\u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0648\u0627\u0631\u06cc\u0632 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
        f"🔢 \u0634\u0646\u0627\u0633\u0647: <code>{tx_id}</code>\n"
        "⏳ \u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc \u062a\u0648\u0633\u0637 \u0627\u062f\u0645\u06cc\u0646...",
        reply_markup=user_main_kb(), parse_mode="HTML"
    )


# ─── My orders ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "u_my_orders")
async def u_my_orders(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        user = await get_user(session, cb.from_user.id)
        if not user: return
        orders = await get_user_orders(session, user.id)

    if not orders:
        await cb.message.edit_text(
            "📦 \u0647\u0646\u0648\u0632 \u0633\u0641\u0627\u0631\u0634\u06cc \u062b\u0628\u062a \u0646\u06a9\u0631\u062f\u0647\u200c\u0627\u06cc\u062f.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
            ]), parse_mode="HTML"
        ); return

    lines = []
    status_icons = {"pending": "⏳", "processing": "🔄", "completed": "✅", "cancelled": "❌", "partial": "⚠️"}
    for o in orders:
        icon = status_icons.get(o.status, "🟡")
        lines.append(f"{icon} <b>#{o.id}</b> {o.service_name[:25]} | ${float(o.charge):.4f}")

    await cb.message.edit_text(
        "📦 <b>\u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627\u06cc \u0627\u062e\u06cc\u0631</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
        ]), parse_mode="HTML"
    )


# ─── Support ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "u_support")
async def u_support(cb: CallbackQuery):
    await cb.answer()
    async with AsyncSessionLocal() as session:
        support = await get_setting(session, "support_username", "")
    text = f"📞 <b>\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc</b>\n\n"
    if support:
        text += f"\u0628\u0631\u0627\u06cc \u0627\u0631\u062a\u0628\u0627\u0637 \u0628\u0627 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc: @{support}"
    else:
        text += "\u062f\u0631 \u062d\u0627\u0644 \u062d\u0627\u0636\u0631 \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc \u0641\u0639\u0627\u0644 \u0646\u06cc\u0633\u062a."
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
        ]), parse_mode="HTML"
    )
