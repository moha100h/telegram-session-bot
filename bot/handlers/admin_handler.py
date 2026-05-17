"""
Admin panel — full featured.
Deposits, users, orders, settings, SMMPass, broadcast, admin management.
"""
import json
import logging
import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User, AdminUser
from services.user_service import (
    get_all_users, get_user_by_id, ban_user, unban_user,
    add_balance, is_admin, get_all_admins,
)
from services.deposit_service import (
    get_pending_deposits, approve_deposit, reject_deposit,
)
from services.order_service import (
    get_all_orders, get_order_by_id, update_order_status, process_refund,
    get_user_orders,
)
from services.settings_service import get_setting as gs, set_setting as ss

logger   = logging.getLogger("admin")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

ROLES = {
    "superadmin": "👑 سوپرادمین",
    "admin":      "🔑 ادمین",
    "moderator":  "🛡 مدیر",
    "support":    "💬 پشتیبان",
}
ALL_PERMS = {
    "deposits":  "💳 تایید واریز",
    "users":     "👥 مدیریت کاربران",
    "orders":    "📦 مشاهده سفارشات",
    "settings":  "⚙️ تنظیمات",
    "broadcast": "📢 پیام همگانی",
    "smmpass":   "🚀 SMMPass",
}


async def _is_admin(uid: int, perm: str = None) -> bool:
    if uid == ADMIN_ID:
        return True
    async with AsyncSessionLocal() as session:
        if not await is_admin(session, uid):
            return False
        if perm is None:
            return True
        from sqlalchemy import select
        res = await session.execute(
            select(AdminUser).where(AdminUser.telegram_id == uid)
        )
        au = res.scalar_one_or_none()
        if not au:
            return False
        if au.role in ("superadmin", "admin"):
            return True
        return au.has_perm(perm)


class AdminState(StatesGroup):
    set_setting_val    = State()
    manual_credit_uid  = State()
    manual_credit_amt  = State()
    search_user        = State()
    search_order       = State()   # جستجوی سفارش با ID یا username
    broadcast_text     = State()
    add_admin_uid      = State()
    add_admin_role     = State()
    add_admin_perms    = State()


def admin_menu_kb(uid: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 کاربران",      callback_data="adm_users"),
         InlineKeyboardButton(text="📦 سفارش‌ها",     callback_data="adm_orders")],
        [InlineKeyboardButton(text="💳 واریزها",      callback_data="adm_deposits"),
         InlineKeyboardButton(text="⚙️ تنظیمات",     callback_data="adm_settings")],
        [InlineKeyboardButton(text="🚀 SMMPass",      callback_data="adm_smmpass"),
         InlineKeyboardButton(text="📢 همگانی",       callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 آمار",         callback_data="adm_stats"),
         InlineKeyboardButton(text="🔑 ادمین‌ها",     callback_data="adm_admins")],
        [InlineKeyboardButton(text="🏠 پنل کاربری",  callback_data="user_home")],
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
        reply_markup=admin_menu_kb(cb.from_user.id), parse_mode="HTML"
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
    banned    = sum(1 for u in users if u.is_banned)
    await cb.message.edit_text(
        f"📊 <b>آمار کلی</b>\n\n"
        f"👥 کاربران: <b>{len(users)}</b>  (🚫 {banned} مسدود)\n"
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
    if not await _is_admin(cb.from_user.id, "deposits"):
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
        f"💳 <b>واریزهای در انتظار</b> ({len(deps)} مورد):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.regexp(r"^adm_dep_\d+$"))
async def adm_dep_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "deposits"):
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
        f"📅 تاریخ: <b>{dep.created_at.strftime('%Y-%m-%d %H:%M')}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید",   callback_data=f"adm_dep_ok_{dep_id}"),
             InlineKeyboardButton(text="❌ رد",      callback_data=f"adm_dep_no_{dep_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_deposits")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_dep_ok_"))
async def adm_dep_approve(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "deposits"):
        await cb.answer("⛔️", show_alert=True); return
    dep_id = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import Transaction
    async with AsyncSessionLocal() as session:
        ok, msg_txt = await approve_deposit(session, dep_id)
        await session.commit()
        res = await session.execute(select(Transaction).where(Transaction.id == dep_id))
        dep = res.scalar_one_or_none()
    if ok and dep:
        await cb.answer("✅ تایید شد!", show_alert=True)
        try:
            await cb.bot.send_message(
                dep.user_id,
                f"✅ <b>واریز شما تایید شد!</b>\n"
                f"💵 مبلغ <b>${float(dep.amount):.2f}</b> به حساب شما اضافه شد.\n"
                f"💰 موجودی جدید خود را با /balance مشاهده کنید.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await cb.answer(f"❌ {msg_txt}", show_alert=True)
    await adm_deposits(cb)


@router.callback_query(F.data.startswith("adm_dep_no_"))
async def adm_dep_reject(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "deposits"):
        await cb.answer("⛔️", show_alert=True); return
    dep_id = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import Transaction
    async with AsyncSessionLocal() as session:
        ok, msg_txt = await reject_deposit(session, dep_id)
        await session.commit()
        res = await session.execute(select(Transaction).where(Transaction.id == dep_id))
        dep = res.scalar_one_or_none()
    if ok and dep:
        await cb.answer("❌ رد شد.", show_alert=True)
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
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    from sqlalchemy import select, func
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        total_res  = await session.execute(select(func.count()).select_from(UserModel))
        total      = total_res.scalar() or 0
        banned_res = await session.execute(select(func.count()).select_from(UserModel).where(UserModel.is_banned == True))
        banned     = banned_res.scalar() or 0
        bal_res    = await session.execute(select(func.sum(UserModel.balance)).select_from(UserModel))
        total_bal  = float(bal_res.scalar() or 0)
    await cb.message.edit_text(
        f"👥 <b>مدیریت کاربران</b>\n\n"
        f"📊 کل: <b>{total}</b>  ✅ فعال: <b>{total - banned}</b>  🚫 مسدود: <b>{banned}</b>\n"
        f"💰 مجموع موجودی: <b>${total_bal:.2f}</b>\n\n"
        f"یک عملیات انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 لیست کاربران",   callback_data="adm_users_list_0_all")],
            [InlineKeyboardButton(text="🔍 جستجوی کاربر",   callback_data="adm_user_search")],
            [InlineKeyboardButton(text="💰 شارژ دستی",       callback_data="adm_manual_credit")],
            [InlineKeyboardButton(text="📤 پیام همگانی",     callback_data="adm_broadcast")],
            [InlineKeyboardButton(text="🔙 بازگشت",          callback_data="menu_admin")],
        ]),
        parse_mode="HTML"
    )


def _users_list_kb(users_chunk: list, page: int, total: int,
                   filter_mode: str = "all") -> InlineKeyboardMarkup:
    PAGE = 8
    buttons = []
    for u in users_chunk:
        icon  = "🚫" if u.is_banned else "✅"
        uname = f"@{u.username}" if u.username else f"#{u.telegram_id}"
        bal   = float(u.balance or 0)
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {u.display_name()[:18]} {uname} | ${bal:.2f}",
            callback_data=f"adm_uid_{u.id}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm_users_list_{page-1}_{filter_mode}"))
    pages = max(1, (total + PAGE - 1) // PAGE)
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="noop"))
    if (page + 1) * PAGE < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm_users_list_{page+1}_{filter_mode}"))
    if nav:
        buttons.append(nav)
    f_all    = "✦ همه"    if filter_mode == "all"    else "👥 همه"
    f_banned = "✦ مسدود"  if filter_mode == "banned" else "🚫 مسدود"
    f_rich   = "✦ موجودی" if filter_mode == "rich"   else "💰 موجودی"
    buttons.append([
        InlineKeyboardButton(text=f_all,    callback_data="adm_users_list_0_all"),
        InlineKeyboardButton(text=f_banned, callback_data="adm_users_list_0_banned"),
        InlineKeyboardButton(text=f_rich,   callback_data="adm_users_list_0_rich"),
    ])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm_users_list")
async def adm_users_list_legacy(cb: CallbackQuery):
    """Fallback برای دکمه‌های قدیمی بدون پارامتر."""
    cb.data = "adm_users_list_0_all"
    await adm_users_list(cb)


@router.callback_query(F.data.startswith("adm_users_list_"))
async def adm_users_list(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    parts       = cb.data.split("_")
    page        = int(parts[3]) if len(parts) > 3 else 0
    filter_mode = parts[4]      if len(parts) > 4 else "all"
    PAGE        = 8

    from sqlalchemy import select, desc
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        q = select(UserModel)
        if filter_mode == "banned":
            q = q.where(UserModel.is_banned == True).order_by(desc(UserModel.created_at))
        elif filter_mode == "rich":
            q = q.order_by(desc(UserModel.balance))
        else:
            q = q.order_by(desc(UserModel.created_at))
        res   = await session.execute(q)
        users = res.scalars().all()

    total = len(users)
    chunk = users[page * PAGE: (page + 1) * PAGE]
    labels = {"all": "همه", "banned": "مسدود", "rich": "بیشترین موجودی"}

    await cb.message.edit_text(
        f"👥 <b>لیست کاربران</b> — {labels.get(filter_mode,'همه')}\n"
        f"📊 {total} کاربر | صفحه {page+1}\n\n"
        f"روی هر کاربر کلیک کنید 👇",
        reply_markup=_users_list_kb(chunk, page, total, filter_mode),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_user_search")
async def adm_user_search_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.search_user)
    await cb.message.edit_text(
        "🔍 <b>جستجوی کاربر</b>\n\n"
        "یوزرنیم، نام یا آیدی عددی تلگرام را وارد کنید:\n\n"
        "/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.search_user)
async def adm_user_search_handle(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    query = msg.text.strip().lstrip("@")
    await state.clear()
    from sqlalchemy import select, or_
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        if query.isdigit():
            res = await session.execute(
                select(UserModel).where(UserModel.telegram_id == int(query))
            )
        else:
            res = await session.execute(
                select(UserModel).where(
                    or_(
                        UserModel.username.ilike(f"%{query}%"),
                        UserModel.first_name.ilike(f"%{query}%"),
                    )
                )
            )
        users = res.scalars().all()
    if not users:
        await msg.answer(
            "❌ کاربری یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")]
            ])
        ); return
    buttons = []
    for u in users[:8]:
        icon  = "🚫" if u.is_banned else "✅"
        uname = f"@{u.username}" if u.username else f"#{u.telegram_id}"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {u.display_name()[:18]} {uname} | ${float(u.balance or 0):.2f}",
            callback_data=f"adm_uid_{u.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")])
    await msg.answer(
        f"🔍 <b>{len(users)} نتیجه</b> برای «{query}»:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_uid_"))
async def adm_user_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    from services.order_service import get_user_orders
    from services.deposit_service import get_user_transactions
    async with AsyncSessionLocal() as session:
        u      = await get_user_by_id(session, uid)
        orders = await get_user_orders(session, uid)
        txns   = await get_user_transactions(session, uid)
    if not u:
        await cb.answer("کاربر یافت نشد!", show_alert=True); return
    uname       = f"@{u.username}" if u.username else "—"
    total_ord   = len(orders)
    done_ord    = sum(1 for o in orders if o.status == "completed")
    active_ord  = sum(1 for o in orders if o.status in ("pending","processing","in progress"))
    total_dep   = sum(float(t.amount or 0) for t in txns if t.type == "deposit" and t.status == "approved")
    total_spent = sum(float(o.sell_price or 0) for o in orders)
    last_order  = orders[0].created_at.strftime("%Y-%m-%d") if orders else "—"
    await cb.message.edit_text(
        f"👤 <b>{u.display_name()}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"🆔 TG ID: <code>{u.telegram_id}</code>\n"
        f"👤 یوزرنیم: {uname}\n"
        f"📱 شماره: {u.phone or '—'}\n"
        f"📅 عضویت: {u.created_at.strftime('%Y-%m-%d')}\n"
        f"🔗 معرفی‌ها: <b>{u.referral_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💰 موجودی: <b>${float(u.balance or 0):.4f}</b>\n"
        f"💳 کل واریز: <b>${total_dep:.2f}</b>\n"
        f"🛒 کل خرید: <b>${total_spent:.4f}</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📦 سفارشات: <b>{total_ord}</b>  ✅ {done_ord}  ⏳ {active_ord}\n"
        f"🕐 آخرین سفارش: {last_order}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{'🚫 <b>مسدود</b>' if u.is_banned else '✅ <b>فعال</b>'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 شارژ",         callback_data=f"adm_credit_{u.id}"),
             InlineKeyboardButton(text="💸 کسر",          callback_data=f"adm_debit_{u.id}")],
            [InlineKeyboardButton(text="📦 سفارشات",      callback_data=f"adm_uorders_{u.id}"),
             InlineKeyboardButton(text="💳 تراکنش‌ها",    callback_data=f"adm_utxns_{u.id}")],
            [InlineKeyboardButton(text="✉️ پیام مستقیم",  callback_data=f"adm_msg_{u.id}"),
             InlineKeyboardButton(
                text="🚫 مسدود" if not u.is_banned else "✅ رفع مسدودی",
                callback_data=f"adm_toggleban_{u.id}"
            )],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_users")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_toggleban_"))
async def adm_toggle_ban(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
        if not u:
            await cb.answer("کاربر یافت نشد!", show_alert=True); return
        if u.is_banned:
            await unban_user(session, u.telegram_id)
            await cb.answer("✅ رفع مسدودی شد.")
            try: await cb.bot.send_message(u.telegram_id, "✅ حساب شما از مسدودی خارج شد.")
            except Exception: pass
        else:
            await ban_user(session, u.telegram_id)
            await cb.answer("🚫 مسدود شد.")
            try: await cb.bot.send_message(u.telegram_id, "🚫 حساب شما مسدود شد. با پشتیبانی تماس بگیرید.")
            except Exception: pass
        await session.commit()
    cb.data = f"adm_uid_{uid}"
    await adm_user_detail(cb)


@router.callback_query(F.data.startswith("adm_credit_"))
async def adm_credit_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
    if not u:
        await cb.answer("کاربر یافت نشد!", show_alert=True); return
    await state.update_data(credit_uid=uid, credit_op="add")
    await state.set_state(AdminState.manual_credit_amt)
    await cb.answer()
    await cb.message.edit_text(
        f"💰 <b>شارژ موجودی</b>\n\n"
        f"👤 {u.display_name()}  (@{u.username or u.telegram_id})\n"
        f"💳 موجودی فعلی: <b>${float(u.balance or 0):.4f}</b>\n\n"
        f"مبلغ شارژ (دلار) را وارد کنید:\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_debit_"))
async def adm_debit_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
    if not u:
        await cb.answer("کاربر یافت نشد!", show_alert=True); return
    await state.update_data(credit_uid=uid, credit_op="debit")
    await state.set_state(AdminState.manual_credit_amt)
    await cb.answer()
    await cb.message.edit_text(
        f"💸 <b>کسر موجودی</b>\n\n"
        f"👤 {u.display_name()}  (@{u.username or u.telegram_id})\n"
        f"💳 موجودی فعلی: <b>${float(u.balance or 0):.4f}</b>\n\n"
        f"مبلغ کسر (دلار، عدد مثبت) را وارد کنید:\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.manual_credit_amt)
async def adm_credit_handle(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        amount = float(msg.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد مثبت وارد کنید."); return
    data = await state.get_data()
    uid  = data.get("credit_uid")
    op   = data.get("credit_op", "add")
    await state.clear()
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
        if not u:
            await msg.answer("❌ کاربر یافت نشد."); return
        if op == "debit":
            ok = await deduct_balance(session, u.id, amount)
            if not ok:
                await msg.answer("❌ موجودی کافی نیست."); return
            new_bal = float(u.balance or 0) - amount
            action_fa = "کسر شد ⬇️"
            sign = "-"
        else:
            await add_balance(session, u.id, amount)
            new_bal = float(u.balance or 0) + amount
            action_fa = "اضافه شد ✅"
            sign = "+"
        await session.commit()
    await msg.answer(
        f"{'✅' if op=='add' else '⬇️'} <b>{sign}${amount:.2f}</b> به <b>{u.display_name()}</b> {action_fa}\n"
        f"💰 موجودی جدید: <b>${new_bal:.4f}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 پروفایل کاربر", callback_data=f"adm_uid_{uid}")]
        ])
    )
    try:
        note = f"💰 <b>+${amount:.2f}</b> به موجودی شما اضافه شد!" if op == "add" else f"⬇️ <b>-${amount:.2f}</b> از موجودی شما کسر شد."
        await msg.bot.send_message(
            u.telegram_id,
            f"{note}\n💳 موجودی جدید: <b>${new_bal:.4f}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data == "adm_manual_credit")
async def adm_manual_credit_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.manual_credit_uid)
    await cb.message.edit_text(
        "💰 <b>شارژ دستی</b>\n\n"
        "یوزرنیم یا آیدی عددی تلگرام کاربر را وارد کنید:\n\n"
        "/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.manual_credit_uid)
async def adm_manual_credit_uid(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    query = msg.text.strip().lstrip("@")
    from sqlalchemy import select, or_
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        if query.isdigit():
            res = await session.execute(select(UserModel).where(UserModel.telegram_id == int(query)))
            u   = res.scalar_one_or_none()
        else:
            res = await session.execute(select(UserModel).where(UserModel.username.ilike(f"%{query}%")))
            users = res.scalars().all()
            u = users[0] if users else None
    if not u:
        await msg.answer("❌ کاربر یافت نشد."); return
    await state.update_data(credit_uid=u.id, credit_op="add")
    await state.set_state(AdminState.manual_credit_amt)
    await msg.answer(
        f"👤 <b>{u.display_name()}</b>  (@{u.username or u.telegram_id})\n"
        f"💰 موجودی فعلی: <b>${float(u.balance or 0):.4f}</b>\n\n"
        "مبلغ شارژ (دلار) را وارد کنید:\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_uorders_"))
async def adm_user_orders(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, uid)
        u      = await get_user_by_id(session, uid)
    if not orders:
        await cb.message.edit_text(
            f"📦 <b>{u.display_name() if u else uid}</b>\n\nهیچ سفارشی ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_uid_{uid}")]
            ]),
            parse_mode="HTML"
        ); return
    ST = {"pending":"⏳","processing":"🔄","in progress":"🔄",
          "completed":"✅","partial":"⚠️","cancelled":"❌","failed":"💔","refunded":"↩️"}
    total_spent = sum(float(o.sell_price or 0) for o in orders)
    done        = sum(1 for o in orders if o.status == "completed")
    rows = []
    for o in orders[:15]:
        icon = ST.get(o.status, "🟡")
        rows.append(
            f"{icon} <b>#{o.id}</b> {o.service_name[:22]}\n"
            f"   🔢 {o.quantity:,}  💰 ${float(o.sell_price):.4f}  📅 {o.created_at.strftime('%m/%d %H:%M')}"
        )
    await cb.message.edit_text(
        f"📦 <b>سفارشات {u.display_name() if u else uid}</b>\n"
        f"📊 کل: {len(orders)}  ✅ {done}  💰 ${total_spent:.4f}\n\n"
        + "\n\n".join(rows),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_uid_{uid}")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_utxns_"))
async def adm_user_txns(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    uid = int(cb.data.split("_")[-1])
    from services.deposit_service import get_user_transactions
    async with AsyncSessionLocal() as session:
        txns = await get_user_transactions(session, uid)
        u    = await get_user_by_id(session, uid)
    if not txns:
        await cb.message.edit_text(
            f"💳 <b>{u.display_name() if u else uid}</b>\n\nهیچ تراکنشی ندارد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_uid_{uid}")]
            ]),
            parse_mode="HTML"
        ); return
    TYPE_FA = {"deposit":"واریز","order":"سفارش","refund":"برگشت","manual":"دستی","debit":"کسر"}
    ST_FA   = {"approved":"✅","pending":"⏳","rejected":"❌"}
    rows    = []
    for t in txns[:15]:
        st   = ST_FA.get(t.status, "🟡")
        tp   = TYPE_FA.get(t.type, t.type)
        sign = "+" if t.type in ("deposit","refund","manual") else "-"
        rows.append(
            f"{st} <b>{sign}${float(t.amount):.4f}</b>  {tp}  "
            f"<i>{t.created_at.strftime('%m/%d %H:%M')}</i>"
        )
    await cb.message.edit_text(
        f"💳 <b>تراکنش‌های {u.display_name() if u else uid}</b>\n\n"
        + "\n".join(rows),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_uid_{uid}")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_msg_"))
async def adm_msg_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    uid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, uid)
    if not u:
        await cb.answer("کاربر یافت نشد!", show_alert=True); return
    await state.update_data(msg_tgid=u.telegram_id, msg_uid=uid, msg_name=u.display_name())
    await state.set_state(AdminState.broadcast_text)
    await cb.answer()
    await cb.message.edit_text(
        f"✉️ <b>پیام مستقیم به {u.display_name()}</b>\n\n"
        f"متن پیام را وارد کنید (HTML پشتیبانی می‌شود):\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "users"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.update_data(msg_tgid=None, msg_uid=None, msg_name="همه کاربران")
    await state.set_state(AdminState.broadcast_text)
    await cb.message.edit_text(
        "📤 <b>پیام همگانی</b>\n\n"
        "متن پیام را وارد کنید (HTML پشتیبانی می‌شود):\n\n"
        "/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.broadcast_text)
async def adm_broadcast_handle(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    data = await state.get_data()
    tgid = data.get("msg_tgid")
    name = data.get("msg_name", "")
    text = msg.text.strip()
    await state.clear()
    if tgid:
        try:
            await msg.bot.send_message(tgid, text, parse_mode="HTML")
            await msg.answer(
                f"✅ پیام به <b>{name}</b> ارسال شد.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="👤 پروفایل", callback_data=f"adm_uid_{data.get('msg_uid')}")]
                ])
            )
        except Exception as e:
            await msg.answer(f"❌ خطا در ارسال: {e}")
    else:
        from sqlalchemy import select
        from db.models import User as UserModel
        import asyncio
        async with AsyncSessionLocal() as session:
            res   = await session.execute(select(UserModel).where(UserModel.is_banned == False))
            users = res.scalars().all()
        sent = failed = 0
        for u in users:
            try:
                await msg.bot.send_message(u.telegram_id, text, parse_mode="HTML")
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)
        await msg.answer(
            f"📤 <b>پیام همگانی ارسال شد</b>\n\n"
            f"✅ موفق: <b>{sent}</b>  ❌ ناموفق: <b>{failed}</b>",
            parse_mode="HTML"
        )


# ── Orders ────────────────────────────────────────────────────────────────────
ADM_ORDER_ST = {
    "pending":    ("⏳", "در صف"),
    "processing": ("🔄", "در حال انجام"),
    "in progress":("🔄", "در حال انجام"),
    "completed":  ("✅", "تکمیل شده"),
    "partial":    ("⚠️", "ناقص"),
    "cancelled":  ("❌", "کنسل شده"),
    "failed":     ("💔", "ناموفق"),
    "refunded":   ("↩️", "برگشت خورده"),
}


def _progress_bar(done: int, total: int, length: int = 10) -> str:
    if total <= 0: return "░" * length
    filled = min(length, int(done / total * length))
    return "█" * filled + "░" * (length - filled)


# ── helpers ───────────────────────────────────────────────────────────────────
def _orders_keyboard(orders: list, back_cb: str = "menu_admin",
                     filter_status: str = "all", page: int = 0) -> InlineKeyboardMarkup:
    """لیست سفارشات با فیلتر وضعیت و صفحه‌بندی."""
    PAGE_SIZE = 15
    filtered = [o for o in orders if filter_status == "all" or o.status == filter_status]
    total    = len(filtered)
    chunk    = filtered[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

    buttons = []
    for o in chunk:
        icon, lbl = ADM_ORDER_ST.get(o.status, ("🟡", o.status))
        name      = (o.service_name or "")[:20]
        buttons.append([InlineKeyboardButton(
            text=f"{icon} #{o.id} | {name} | {o.quantity:,} | {lbl}",
            callback_data=f"adm_order_{o.id}"
        )])

    # صفحه‌بندی
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی",
                   callback_data=f"adm_orders_pg_{filter_status}_{page-1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="بعدی ▶️",
                   callback_data=f"adm_orders_pg_{filter_status}_{page+1}"))
    if nav:
        buttons.append(nav)

    # فیلتر سریع
    filter_row = [
        InlineKeyboardButton(text="🔍 سرچ",     callback_data="adm_order_search"),
        InlineKeyboardButton(text="⏳ در صف",    callback_data="adm_orders_pg_pending_0"),
        InlineKeyboardButton(text="🔄 در انجام", callback_data="adm_orders_pg_processing_0"),
        InlineKeyboardButton(text="✅ تکمیل",    callback_data="adm_orders_pg_completed_0"),
    ]
    buttons.append(filter_row)
    buttons.append([
        InlineKeyboardButton(text="⚠️ ناقص",  callback_data="adm_orders_pg_partial_0"),
        InlineKeyboardButton(text="❌ کنسل",   callback_data="adm_orders_pg_cancelled_0"),
        InlineKeyboardButton(text="📋 همه",    callback_data="adm_orders_pg_all_0"),
    ])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "adm_orders")
async def adm_orders(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        orders = await get_all_orders(session)
    if not orders:
        await cb.message.edit_text(
            "📦 <b>سفارشات</b>\n\nهیچ سفارشی ثبت نشده.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")]
            ]),
            parse_mode="HTML"
        ); return

    completed = sum(1 for o in orders if o.status == "completed")
    pending   = sum(1 for o in orders if o.status in ("pending", "processing", "in progress"))
    revenue   = sum(float(o.sell_price or 0) for o in orders)

    await cb.message.edit_text(
        f"📦 <b>سفارشات</b>\n\n"
        f"📊 کل: <b>{len(orders)}</b>  ✅ تکمیل: <b>{completed}</b>  "
        f"⏳ در جریان: <b>{pending}</b>\n"
        f"💰 مجموع درآمد: <b>${revenue:.4f}</b>\n\n"
        f"فیلتر یا روی سفارش کلیک کنید 👇",
        reply_markup=_orders_keyboard(orders, back_cb="menu_admin"),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_orders_pg_"))
async def adm_orders_paged(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    # adm_orders_pg_{filter}_{page}
    parts         = cb.data.split("_")
    filter_status = parts[3]
    page          = int(parts[4])
    async with AsyncSessionLocal() as session:
        orders = await get_all_orders(session)
    filtered = [o for o in orders if filter_status == "all" or o.status == filter_status]
    label_map = {
        "all": "همه", "pending": "در صف", "processing": "در انجام",
        "completed": "تکمیل", "partial": "ناقص", "cancelled": "کنسل",
    }
    lbl = label_map.get(filter_status, filter_status)
    await cb.message.edit_text(
        f"📦 <b>سفارشات — {lbl}</b> ({len(filtered)} مورد)\n\n"
        f"روی سفارش کلیک کنید 👇",
        reply_markup=_orders_keyboard(orders, back_cb="menu_admin",
                                      filter_status=filter_status, page=page),
        parse_mode="HTML"
    )


# ── جستجوی سفارش ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_order_search")
async def adm_order_search_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.search_order)
    await cb.message.edit_text(
        "🔍 <b>جستجوی سفارش</b>\n\n"
        "شناسه سفارش (مثال: <code>42</code>) یا "
        "یوزرنیم/آیدی کاربر (مثال: <code>@user</code> یا <code>123456</code>) را وارد کنید:\n\n"
        "/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.search_order)
async def adm_order_search_handle(msg: Message, state: FSMContext):
    if not await _is_admin(msg.from_user.id, "orders"): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        await msg.answer("❌ لغو شد."); return

    query = (msg.text or "").strip()
    await state.clear()

    from sqlalchemy import select
    from db.models import Order as OrderModel

    async with AsyncSessionLocal() as session:
        # جستجو با ID سفارش
        if query.isdigit():
            res = await session.execute(
                select(OrderModel).where(OrderModel.id == int(query))
            )
            orders = [o for o in [res.scalar_one_or_none()] if o]
            if not orders:
                # شاید آیدی کاربر باشه
                res2 = await session.execute(
                    select(OrderModel)
                    .where(OrderModel.user_id == int(query))
                    .order_by(OrderModel.created_at.desc())
                    .limit(20)
                )
                orders = list(res2.scalars().all())
        elif query.startswith("@"):
            uname = query.lstrip("@")
            u_res = await session.execute(
                select(User).where(User.username == uname)
            )
            u = u_res.scalar_one_or_none()
            if u:
                res = await session.execute(
                    select(OrderModel)
                    .where(OrderModel.user_id == u.id)
                    .order_by(OrderModel.created_at.desc())
                    .limit(20)
                )
                orders = list(res.scalars().all())
            else:
                orders = []
        else:
            orders = []

    if not orders:
        await msg.answer(
            f"❌ <b>نتیجه‌ای یافت نشد</b> برای: <code>{query}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 جستجوی مجدد", callback_data="adm_order_search")],
                [InlineKeyboardButton(text="🔙 بازگشت",       callback_data="adm_orders")],
            ]),
            parse_mode="HTML"
        ); return

    if len(orders) == 1:
        # مستقیم جزئیات
        await msg.answer(
            f"✅ سفارش #{orders[0].id} یافت شد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"📦 مشاهده سفارش #{orders[0].id}",
                                      callback_data=f"adm_order_{orders[0].id}")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_orders")],
            ])
        ); return

    buttons = []
    for o in orders[:20]:
        icon, lbl = ADM_ORDER_ST.get(o.status, ("🟡", o.status))
        name      = (o.service_name or "")[:20]
        buttons.append([InlineKeyboardButton(
            text=f"{icon} #{o.id} | {name} | {o.quantity:,} | {lbl}",
            callback_data=f"adm_order_{o.id}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_orders")])
    await msg.answer(
        f"🔍 <b>نتایج جستجو</b> برای <code>{query}</code>: {len(orders)} سفارش",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


# ── جزئیات سفارش (ادمین) ──────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^adm_order_\d+$"))
async def adm_order_live(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer("🔄 در حال دریافت وضعیت...")
    order_id = int(cb.data.split("_")[-1])

    from services.smmpass import get_order_status as api_get_status

    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)
    if not order:
        await cb.answer("❌ سفارش یافت نشد!", show_alert=True); return

    live_status  = order.status
    live_start   = order.start_count
    live_remains = order.remains
    api_error    = None
    refunded     = 0.0

    # ── دریافت وضعیت از API با api_order_id صحیح ─────────────────────────────
    api_id = order.api_order_id
    if api_id and str(api_id).isdigit():
        try:
            data         = await api_get_status(int(api_id))
            live_status  = str(data.get("status", order.status)).lower()
            live_start   = data.get("start_count", order.start_count)
            live_remains = data.get("remains",     order.remains)

            async with AsyncSessionLocal() as session:
                updated = await update_order_status(
                    session, order_id, live_status,
                    start_count = int(live_start)   if live_start   is not None else None,
                    remains     = int(live_remains) if live_remains is not None else None,
                )
                if updated and live_status in ("cancelled", "partial") and order.status != live_status:
                    refunded = await process_refund(session, updated)
                    if refunded > 0:
                        try:
                            await cb.bot.send_message(
                                order.user_id,
                                f"↩️ <b>برگشت وجه</b>\n"
                                f"سفارش #{order.id} "
                                f"{ADM_ORDER_ST.get(live_status, ('',''))[1]} شد.\n"
                                f"💰 <b>${refunded:.4f}</b> به موجودی شما برگشت.",
                                parse_mode="HTML"
                            )
                        except Exception:
                            pass
                await session.commit()
        except Exception as e:
            api_error = str(e)[:120]
    else:
        api_error = "⚠️ api_order_id ثبت نشده (سفارش قدیمی)"

    # ── محاسبه progress ───────────────────────────────────────────────────────
    icon, label = ADM_ORDER_ST.get(live_status, ("🟡", live_status))
    done = pct = 0
    try:
        if live_start is not None and live_remains is not None:
            done = max(0, int(live_start) - int(live_remains))
            pct  = min(100, int(done / order.quantity * 100)) if order.quantity > 0 else 0
    except Exception:
        pass
    bar = _progress_bar(done, order.quantity)

    # ── اطلاعات کاربر ────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        u = await get_user_by_id(session, order.user_id)
    uname    = f"@{u.username}" if u and u.username else f"uid:{order.user_id}"
    bal_info = f"  💰 موجودی: <b>${float(u.balance or 0):.4f}</b>" if u else ""

    # ── متن پیام ─────────────────────────────────────────────────────────────
    text = (
        f"📦 <b>سفارش #{order.id}</b>\n\n"
        f"👤 کاربر: <b>{uname}</b>{bal_info}\n"
        f"🛒 سرویس: <b>{order.service_name}</b>\n"
        f"🔗 لینک: <code>{order.link}</code>\n"
        f"🔢 تعداد: <b>{order.quantity:,}</b>\n"
        f"💰 فروش: <b>${float(order.sell_price):.4f}</b>  "
        f"💹 هزینه: <b>${float(order.cost_price):.4f}</b>\n"
        f"📅 ثبت: <b>{order.created_at.strftime('%Y-%m-%d %H:%M')}</b>\n"
    )
    if api_id:
        text += f"🌐 شناسه API: <code>{api_id}</code>\n"

    text += f"\n━━━━━━━━━━━━━━━━━\n{icon} وضعیت: <b>{label}</b>\n"

    if live_start is not None:
        text += f"🔢 شروع از: <b>{int(live_start):,}</b>\n"
    if live_remains is not None:
        text += f"⏳ باقی‌مانده: <b>{int(live_remains):,}</b>\n"
    if done > 0 or pct > 0:
        text += (
            f"✅ انجام شده: <b>{done:,}</b> از <b>{order.quantity:,}</b>\n"
            f"📊 <code>[{bar}]</code> <b>{pct}%</b>\n"
        )
    if api_error:
        text += f"\n⚠️ <i>{api_error}</i>\n"
    if refunded > 0:
        text += f"\n↩️ <b>${refunded:.4f} به موجودی کاربر برگشت داده شد.</b>"
    elif live_status == "cancelled":
        text += "\n↩️ <b>سفارش کنسل — پول کاربر برگشت خورد.</b>"
    elif live_status == "partial":
        text += "\n↩️ <b>سفارش ناقص — مابقی برگشت داده شد.</b>"
    elif live_status == "completed":
        text += "\n🎉 <b>سفارش با موفقیت تکمیل شد!</b>"

    # ── دکمه‌ها ───────────────────────────────────────────────────────────────
    can_cancel = live_status in ("pending", "processing", "in progress")
    action_row = []
    if can_cancel:
        action_row.append(InlineKeyboardButton(
            text="🚫 کنسل دستی",
            callback_data=f"adm_ocancel_confirm_{order_id}"
        ))
    action_row.append(InlineKeyboardButton(
        text="🔄 بروزرسانی",
        callback_data=f"adm_order_{order_id}"
    ))

    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            action_row,
            [InlineKeyboardButton(text="🔙 بازگشت به سفارشات", callback_data="adm_orders")],
        ]),
        parse_mode="HTML"
    )


# ── کنسل دستی — تأیید ────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("adm_ocancel_confirm_"))
async def adm_order_cancel_confirm(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    order_id = int(cb.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)
    if not order:
        await cb.answer("❌ سفارش یافت نشد!", show_alert=True); return

    from services.order_service import calc_refund
    refund_est = await calc_refund(order)

    await cb.message.edit_text(
        f"⚠️ <b>تأیید کنسل سفارش #{order_id}</b>\n\n"
        f"🛒 سرویس: <b>{order.service_name}</b>\n"
        f"🔢 تعداد: <b>{order.quantity:,}</b>\n"
        f"💰 مبلغ پرداختی: <b>${float(order.sell_price):.4f}</b>\n\n"
        f"↩️ برگشت تخمینی به کاربر: <b>${refund_est:.4f}</b>\n\n"
        f"⚠️ این عملیات <b>برگشت‌ناپذیر</b> است. آیا مطمئن هستید؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ بله، کنسل کن",
                                     callback_data=f"adm_ocancel_do_{order_id}"),
                InlineKeyboardButton(text="❌ خیر، برگشت",
                                     callback_data=f"adm_order_{order_id}"),
            ]
        ]),
        parse_mode="HTML"
    )


# ── کنسل دستی — اجرا ─────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("adm_ocancel_do_"))
async def adm_order_do_cancel(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "orders"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer("⏳ در حال کنسل کردن...")
    order_id = int(cb.data.split("_")[-1])

    from services.smmpass import cancel_order as api_cancel

    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)
    if not order:
        await cb.answer("❌ سفارش یافت نشد!", show_alert=True); return

    api_cancel_result = None
    api_cancel_error  = None

    # ── کنسل از API ──────────────────────────────────────────────────────────
    api_id = order.api_order_id
    if api_id and str(api_id).isdigit():
        try:
            api_cancel_result = await api_cancel(int(api_id))
        except Exception as e:
            api_cancel_error = str(e)[:120]
    else:
        api_cancel_error = "api_order_id ثبت نشده — فقط در DB کنسل شد"

    # ── آپدیت DB + refund ────────────────────────────────────────────────────
    refunded = 0.0
    async with AsyncSessionLocal() as session:
        updated = await update_order_status(session, order_id, "cancelled")
        if updated:
            refunded = await process_refund(session, updated)
        await session.commit()

    # ── اطلاع‌رسانی به کاربر ─────────────────────────────────────────────────
    if refunded > 0:
        try:
            await cb.bot.send_message(
                order.user_id,
                f"↩️ <b>سفارش #{order_id} کنسل شد</b>\n\n"
                f"🛒 {order.service_name}\n"
                f"💰 <b>${refunded:.4f}</b> به موجودی شما برگشت داده شد.",
                parse_mode="HTML"
            )
        except Exception:
            pass

    # ── پیام نتیجه به ادمین ──────────────────────────────────────────────────
    result_text = (
        f"✅ <b>سفارش #{order_id} کنسل شد</b>\n\n"
        f"↩️ برگشت به کاربر: <b>${refunded:.4f}</b>\n"
    )
    if api_cancel_result:
        result_text += f"🌐 پاسخ API: <code>{str(api_cancel_result)[:100]}</code>\n"
    if api_cancel_error:
        result_text += f"⚠️ <i>خطای API: {api_cancel_error}</i>\n"

    await cb.message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 بازگشت به سفارشات", callback_data="adm_orders")]
        ]),
        parse_mode="HTML"
    )


# ── Settings ──────────────────────────────────────────────────────────────────
SETTING_KEYS = {
    "adm_set_bot_name":    ("bot_name",           "نام بات"),
    "adm_set_welcome":     ("welcome_message",    "پیام خوش‌آمد"),
    "adm_set_support":     ("support_url",        "لینک/یوزرنیم پشتیبانی"),
    "adm_set_wallet_usdt": ("wallet_usdt",        "آدرس USDT"),
    "adm_set_wallet_ton":  ("wallet_ton",         "آدرس TON"),
    "adm_set_wallet_trx":  ("wallet_trx",         "آدرس TRX"),
    "adm_set_smm_title":   ("smm_panel_title",    "نام دکمه SMM"),
    "adm_set_markup":      ("smm_markup_percent", "درصد سود SMM"),
    "adm_set_apikey":      ("smmpass_api_key",    "API Key سمس‌پس"),
    "adm_set_auto_cancel": ("order_auto_cancel_hours", "ساعت کنسل خودکار سفارش"),
}


@router.callback_query(F.data == "adm_settings")
async def adm_settings(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "settings"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        vals = {}
        for cb_key, (db_key, _) in SETTING_KEYS.items():
            vals[db_key] = await gs(session, db_key, "—")
    api_key_masked = vals["smmpass_api_key"][:6] + "****" if len(vals["smmpass_api_key"]) > 6 else vals["smmpass_api_key"]
    await cb.message.edit_text(
        f"⚙️ <b>تنظیمات</b>\n\n"
        f"🤖 نام بات: <b>{vals['bot_name']}</b>\n"
        f"👋 خوش‌آمد: <i>{vals['welcome_message'][:40]}</i>\n"
        f"📞 پشتیبانی: <b>{vals['support_url']}</b>\n"
        f"🟢 USDT: <code>{vals['wallet_usdt']}</code>\n"
        f"💎 TON: <code>{vals['wallet_ton']}</code>\n"
        f"⚡ TRX: <code>{vals['wallet_trx']}</code>\n"
        f"🚀 نام دکمه SMM: <b>{vals['smm_panel_title']}</b>\n"
        f"💹 درصد سود: <b>{vals['smm_markup_percent']}%</b>\n"
        f"🔑 API Key: <code>{api_key_masked}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 نام بات",        callback_data="adm_set_bot_name"),
             InlineKeyboardButton(text="👋 خوش‌آمد",        callback_data="adm_set_welcome")],
            [InlineKeyboardButton(text="📞 پشتیبانی",       callback_data="adm_set_support"),
             InlineKeyboardButton(text="💹 درصد سود",       callback_data="adm_set_markup")],
            [InlineKeyboardButton(text="🟢 USDT",           callback_data="adm_set_wallet_usdt"),
             InlineKeyboardButton(text="💎 TON",            callback_data="adm_set_wallet_ton")],
            [InlineKeyboardButton(text="⚡ TRX",            callback_data="adm_set_wallet_trx"),
             InlineKeyboardButton(text="🚀 نام دکمه SMM",   callback_data="adm_set_smm_title")],
            [InlineKeyboardButton(text="🔑 API Key سمس‌پس", callback_data="adm_set_apikey"),
             InlineKeyboardButton(text="⏰ کنسل خودکار",    callback_data="adm_set_auto_cancel")],
            [InlineKeyboardButton(text="🔙 بازگشت",         callback_data="menu_admin")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.in_(set(SETTING_KEYS.keys())))
async def adm_set_setting(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id, "settings"):
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
    # اگه API key تغییر کرد، cache رو پاک کن
    if key == "smmpass_api_key":
        from services.smmpass import clear_cache
        clear_cache()
    await msg.answer(
        f"✅ <b>{label}</b> به‌روز شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm_settings")]
        ]),
        parse_mode="HTML"
    )


# ── SMMPass Admin ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_smmpass")
async def adm_smmpass(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "smmpass"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    from services.smmpass import get_services, get_balance, get_categories
    async with AsyncSessionLocal() as session:
        markup    = await gs(session, "smm_markup_percent", "20")
        smm_title = await gs(session, "smm_panel_title", "🚀 پنل SMM")
        api_key   = await gs(session, "smmpass_api_key", "")
    try:
        bal_data = await get_balance()
        api_bal  = f"${bal_data.get('balance','?')} {bal_data.get('currency','USD')}"
    except Exception as e:
        api_bal = f"خطا: {str(e)[:40]}"
    services = await get_services()
    cats     = get_categories(services)
    key_masked = api_key[:6] + "****" if len(api_key) > 6 else "تنظیم نشده"
    await cb.message.edit_text(
        f"🚀 <b>مدیریت SMMPass</b>\n\n"
        f"💰 موجودی API: <b>{api_bal}</b>\n"
        f"📊 سرویس‌ها: <b>{len(services)}</b> در <b>{len(cats)}</b> دسته\n"
        f"💹 درصد سود: <b>{markup}%</b>\n"
        f"🔑 API Key: <code>{key_masked}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 تغییر API Key",   callback_data="adm_set_apikey"),
             InlineKeyboardButton(text="💹 درصد سود",        callback_data="adm_set_markup")],
            [InlineKeyboardButton(text="📋 دسته‌بندی‌ها",   callback_data="adm_sp_cats"),
             InlineKeyboardButton(text="🔄 رفرش سرویس‌ها",  callback_data="adm_sp_refresh")],
            [InlineKeyboardButton(text="📦 سفارشات",         callback_data="adm_orders")],
            [InlineKeyboardButton(text="🔙 بازگشت",          callback_data="menu_admin")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_sp_refresh")
async def adm_sp_refresh(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id, "smmpass"):
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
    if not await _is_admin(cb.from_user.id, "smmpass"):
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
    if not await _is_admin(cb.from_user.id, "broadcast"):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.broadcast_text)
    await cb.message.edit_text(
        "📢 <b>پیام همگانی</b>\n\nمتن پیام را وارد کنید (HTML پشتیبانی می‌شود):\n\n/cancel برای لغو",
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


# ── Admin Management ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_admins")
async def adm_admins(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        admins = await get_all_admins(session)
    lines = [f"👑 <b>سوپرادمین</b>: <code>{ADMIN_ID}</code>"]
    buttons = []
    for a in admins:
        uname = f"@{a.username}" if a.username else f"ID:{a.telegram_id}"
        role_fa = ROLES.get(a.role, a.role)
        lines.append(f"{role_fa} {uname}")
        buttons.append([InlineKeyboardButton(
            text=f"🗑 حذف {uname}",
            callback_data=f"adm_del_admin_{a.telegram_id}"
        )])
    buttons.insert(0, [InlineKeyboardButton(text="➕ افزودن ادمین", callback_data="adm_add_admin")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")])
    await cb.message.edit_text(
        "🔑 <b>مدیریت ادمین‌ها</b>\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_add_admin")
async def adm_add_admin_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️ فقط سوپرادمین", show_alert=True); return
    await cb.answer()
    await state.set_state(AdminState.add_admin_uid)
    await cb.message.edit_text(
        "➕ <b>افزودن ادمین</b>\n\nآیدی عددی تلگرام ادمین جدید را وارد کنید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(AdminState.add_admin_uid)
async def adm_add_admin_uid(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        tg_id = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ آیدی عددی وارد کنید."); return
    await state.update_data(new_admin_id=tg_id)
    await state.set_state(AdminState.add_admin_role)
    await msg.answer(
        "🔑 <b>نقش ادمین را انتخاب کنید:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 ادمین کامل",  callback_data="role_admin")],
            [InlineKeyboardButton(text="🛡 مدیر",         callback_data="role_moderator")],
            [InlineKeyboardButton(text="💬 پشتیبان",      callback_data="role_support")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("role_"), AdminState.add_admin_role)
async def adm_add_admin_role(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️", show_alert=True); return
    role = cb.data.split("_", 1)[1]
    await state.update_data(new_admin_role=role)
    await cb.answer()
    if role == "admin":
        # ادمین کامل — همه دسترسی‌ها
        data = await state.get_data()
        await _create_admin(cb, state, data["new_admin_id"], role, list(ALL_PERMS.keys()))
        return
    # برای moderator/support — انتخاب دسترسی‌ها
    await state.set_state(AdminState.add_admin_perms)
    perm_buttons = []
    for perm_key, perm_label in ALL_PERMS.items():
        perm_buttons.append([InlineKeyboardButton(
            text=perm_label,
            callback_data=f"perm_{perm_key}"
        )])
    perm_buttons.append([InlineKeyboardButton(text="✅ تایید", callback_data="perms_done")])
    await state.update_data(selected_perms=[])
    await cb.message.edit_text(
        "🔐 <b>دسترسی‌ها را انتخاب کنید:</b>\n(می‌توانید چند مورد انتخاب کنید)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=perm_buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("perm_"), AdminState.add_admin_perms)
async def adm_toggle_perm(cb: CallbackQuery, state: FSMContext):
    perm = cb.data.split("_", 1)[1]
    data = await state.get_data()
    perms = data.get("selected_perms", [])
    if perm in perms:
        perms.remove(perm)
        await cb.answer(f"❌ {ALL_PERMS.get(perm, perm)} حذف شد")
    else:
        perms.append(perm)
        await cb.answer(f"✅ {ALL_PERMS.get(perm, perm)} اضافه شد")
    await state.update_data(selected_perms=perms)


@router.callback_query(F.data == "perms_done", AdminState.add_admin_perms)
async def adm_perms_done(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️", show_alert=True); return
    data  = await state.get_data()
    tg_id = data.get("new_admin_id")
    role  = data.get("new_admin_role", "support")
    perms = data.get("selected_perms", [])
    await _create_admin(cb, state, tg_id, role, perms)


async def _create_admin(cb: CallbackQuery, state: FSMContext,
                        tg_id: int, role: str, perms: list):
    from sqlalchemy import select
    from db.models import User as UserModel
    async with AsyncSessionLocal() as session:
        # پیدا کردن username
        res = await session.execute(select(UserModel).where(UserModel.telegram_id == tg_id))
        u   = res.scalar_one_or_none()
        uname = u.username if u else None
        # بررسی تکراری نبودن
        res2 = await session.execute(select(AdminUser).where(AdminUser.telegram_id == tg_id))
        existing = res2.scalar_one_or_none()
        if existing:
            existing.role        = role
            existing.permissions = json.dumps({p: True for p in perms})
        else:
            session.add(AdminUser(
                telegram_id = tg_id,
                username    = uname,
                role        = role,
                permissions = json.dumps({p: True for p in perms}),
            ))
        await session.commit()
    await state.clear()
    role_fa  = ROLES.get(role, role)
    perm_txt = " | ".join(ALL_PERMS.get(p, p) for p in perms) or "بدون دسترسی"
    await cb.message.edit_text(
        f"✅ <b>ادمین اضافه شد!</b>\n\n"
        f"🆔 <code>{tg_id}</code>\n"
        f"👤 @{uname or '—'}\n"
        f"🔑 نقش: <b>{role_fa}</b>\n"
        f"🔐 دسترسی‌ها: {perm_txt}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 مدیریت ادمین‌ها", callback_data="adm_admins")]
        ]),
        parse_mode="HTML"
    )
    try:
        await cb.bot.send_message(
            tg_id,
            f"🔑 شما به عنوان <b>{role_fa}</b> در پنل ادمین اضافه شدید.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_del_admin_"))
async def adm_del_admin(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️ فقط سوپرادمین", show_alert=True); return
    tg_id = int(cb.data.split("_")[-1])
    from sqlalchemy import select, delete
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AdminUser).where(AdminUser.telegram_id == tg_id))
        await session.commit()
    await cb.answer("🗑 ادمین حذف شد.", show_alert=True)
    await adm_admins(cb)
