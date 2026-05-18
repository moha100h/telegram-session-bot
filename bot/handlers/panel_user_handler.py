"""
Panel User Handler — نمایش پنل‌های دستی به کاربر و ثبت سفارش.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User
from services.panel_service import (
    get_all_panels, get_panel, get_categories, get_services, get_service,
    create_panel_order, process_panel_refund,
)
from services.notification_service import notify_balance_deducted, notify_order_status
from services.user_service import deduct_balance, add_balance

logger = logging.getLogger("panel_user")
router = Router()


class PanelUserState(StatesGroup):
    order_qty  = State()
    order_link = State()
    order_note = State()


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data="user_home")]
    ])


# ── لیست دسته‌بندی‌های پنل ───────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_user_\d+$"))
async def panel_user_cats(cb: CallbackQuery):
    await cb.answer()
    pid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        panel = await get_panel(s, pid)
        cats  = await get_categories(s, pid, active_only=True)
    if not panel or not panel.is_active:
        await cb.message.edit_text("❌ این پنل در دسترس نیست.",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                       [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
                                   ])); return
    rows = []
    for cat in cats:
        rows.append([InlineKeyboardButton(
            text=f"{cat.icon} {cat.name}",
            callback_data=f"panel_cat_{cat.id}_{pid}"
        )])
    rows.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])
    desc = f"\n<i>{panel.description}</i>" if panel.description else ""
    await cb.message.edit_text(
        f"{panel.button_label}\n{'━'*28}{desc}\n\n"
        "یک دسته‌بندی را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


# ── لیست خدمات دسته ──────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_cat_\d+_\d+$"))
async def panel_user_svcs(cb: CallbackQuery):
    await cb.answer()
    parts = cb.data.split("_")
    cid, pid = int(parts[2]), int(parts[3])
    from sqlalchemy import select
    from db.models import PanelCategory
    async with AsyncSessionLocal() as s:
        res  = await s.execute(select(PanelCategory).where(PanelCategory.id == cid))
        cat  = res.scalar_one_or_none()
        svcs = await get_services(s, cid, active_only=True)
    if not cat:
        await cb.message.edit_text("❌ دسته یافت نشد.",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                       [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"panel_user_{pid}")]
                                   ])); return
    rows = []
    for svc in svcs:
        rows.append([InlineKeyboardButton(
            text=f"📌 {svc.name} — ${svc.price:.2f}/واحد",
            callback_data=f"panel_svc_{svc.id}_{pid}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"panel_user_{pid}")])
    await cb.message.edit_text(
        f"{cat.icon} <b>{cat.name}</b>\n{'━'*28}\n\n"
        "یک خدمت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


# ── جزئیات خدمت ──────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_svc_\d+_\d+$"))
async def panel_user_svc_detail(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await cb.answer()
    parts = cb.data.split("_")
    sid, pid = int(parts[2]), int(parts[3])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
    if not svc or not svc.is_active:
        await cb.message.edit_text("❌ این خدمت در دسترس نیست.",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                       [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"panel_user_{pid}")]
                                   ])); return
    bal = float(db_user.balance or 0) if db_user else 0
    await state.update_data(pu_svc_id=sid, pu_panel_id=pid,
                            pu_svc_name=svc.name, pu_price=svc.price,
                            pu_min=svc.min_qty, pu_max=svc.max_qty)
    await cb.message.edit_text(
        f"📌 <b>{svc.name}</b>\n{'━'*28}\n"
        + (f"📄 {svc.description}\n" if svc.description else "") +
        f"💰 قیمت: <b>${svc.price:.4f}</b> / واحد\n"
        f"📊 حداقل: <b>{svc.min_qty:,}</b> | حداکثر: <b>{svc.max_qty:,}</b>\n"
        f"💳 موجودی شما: <b>${bal:.2f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش دهید", callback_data=f"panel_order_start_{sid}_{pid}")],
            [InlineKeyboardButton(text="🔙 بازگشت",      callback_data=f"panel_cat_{svc.category_id}_{pid}")],
        ]),
        parse_mode="HTML"
    )


# ── شروع سفارش ───────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_order_start_\d+_\d+$"))
async def panel_order_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split("_")
    sid, pid = int(parts[3]), int(parts[4])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
    await state.update_data(pu_svc_id=sid, pu_panel_id=pid,
                            pu_svc_name=svc.name, pu_price=svc.price,
                            pu_min=svc.min_qty, pu_max=svc.max_qty)
    await state.set_state(PanelUserState.order_link)
    await cb.message.edit_text(
        f"🛒 <b>{svc.name}</b>\n{'━'*28}\n\n"
        "🔗 <b>لینک یا یوزرنیم مقصد را وارد کنید:</b>\n"
        "<i>مثال: https://t.me/channel یا @username</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML"
    )


@router.message(PanelUserState.order_link)
async def panel_order_link(msg: Message, state: FSMContext):
    link = (msg.text or "").strip()
    if not link:
        await msg.answer("❌ لینک نمی‌تواند خالی باشد.", reply_markup=_cancel_kb()); return
    await state.update_data(pu_link=link)
    await state.set_state(PanelUserState.order_qty)
    data = await state.get_data()
    mn, mx = data.get("pu_min", 1), data.get("pu_max", 10000)
    price  = data.get("pu_price", 0)
    await msg.answer(
        f"🔢 <b>تعداد را وارد کنید:</b>\n{'━'*28}\n\n"
        f"📊 حداقل: <b>{mn:,}</b> | حداکثر: <b>{mx:,}</b>\n"
        f"💰 قیمت: <b>${price:.4f}</b> / واحد\n\n"
        "<i>فقط عدد — مثال: 1000</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML"
    )


@router.message(PanelUserState.order_qty)
async def panel_order_qty(msg: Message, state: FSMContext, db_user: User = None):
    try:
        qty = int((msg.text or "").strip().replace(",", ""))
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.", reply_markup=_cancel_kb()); return
    data = await state.get_data()
    mn, mx = data.get("pu_min", 1), data.get("pu_max", 10000)
    if qty < mn or qty > mx:
        await msg.answer(f"❌ تعداد باید بین <b>{mn:,}</b> و <b>{mx:,}</b> باشد.",
                         reply_markup=_cancel_kb(), parse_mode="HTML"); return
    await state.update_data(pu_qty=qty)
    await state.set_state(PanelUserState.order_note)
    await msg.answer(
        "📝 <b>توضیح اضافه (اختیاری):</b>\n"
        "<i>برای رد کردن /skip بزنید</i>",
        reply_markup=_cancel_kb(),
        parse_mode="HTML"
    )


@router.message(PanelUserState.order_note)
async def panel_order_note(msg: Message, state: FSMContext, db_user: User = None):
    note = "" if (msg.text or "").strip() == "/skip" else (msg.text or "").strip()
    await state.update_data(pu_note=note)
    data  = await state.get_data()
    qty   = data.get("pu_qty", 1)
    price = data.get("pu_price", 0)
    total = round(price * qty, 6)
    bal   = float(db_user.balance or 0) if db_user else 0
    bal_ok= bal >= total
    svc_name = data.get("pu_svc_name", "")
    link     = data.get("pu_link", "")

    text = (
        f"📋 <b>تایید سفارش</b>\n{'━'*28}\n"
        f"📌 خدمت: <b>{svc_name[:50]}</b>\n"
        f"🔗 لینک: <code>{link}</code>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        + (f"📝 توضیح: <i>{note}</i>\n" if note else "") +
        f"{'━'*28}\n"
        f"💰 هزینه: <b>${total:.4f}</b>\n"
        f"💳 موجودی: <b>${bal:.2f}</b>\n\n"
    )
    text += "✅ موجودی کافی است." if bal_ok else "❌ موجودی ناکافی."
    rows = []
    if bal_ok:
        rows.append([InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="panel_confirm")])
    else:
        rows.append([InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")])
    rows.append([InlineKeyboardButton(text="❌ لغو", callback_data="user_home")])
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


# ── تایید و ثبت سفارش ────────────────────────────────────────────────────────
@router.callback_query(F.data == "panel_confirm")
async def panel_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot, db_user: User = None):
    await cb.answer()
    data     = await state.get_data()
    svc_id   = data.get("pu_svc_id")
    panel_id = data.get("pu_panel_id")
    svc_name = data.get("pu_svc_name", "")
    qty      = data.get("pu_qty", 1)
    price    = data.get("pu_price", 0)
    total    = round(price * qty, 6)
    link     = data.get("pu_link", "")
    note     = data.get("pu_note", "")

    if not db_user:
        await cb.message.edit_text("❌ خطا: کاربر یافت نشد."); return

    bal = float(db_user.balance or 0)
    if bal < total:
        await cb.message.edit_text(
            "❌ <b>موجودی ناکافی!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")],
                [InlineKeyboardButton(text="🏠 بازگشت",       callback_data="user_home")],
            ]),
            parse_mode="HTML"
        ); return

    await cb.message.edit_text("⏳ <b>در حال ثبت سفارش...</b>", parse_mode="HTML")

    async with AsyncSessionLocal() as s:
        ok = await deduct_balance(s, db_user.id, total)
        if not ok:
            await cb.message.edit_text("❌ خطا در کسر موجودی."); return
        await s.commit()

        # دریافت اسم پنل
        panel = await get_panel(s, panel_id)
        panel_name = panel.button_label if panel else ""
        group_id   = panel.group_chat_id if panel else None

        order = await create_panel_order(
            s, db_user.id, panel_id, svc_id, svc_name, panel_name,
            qty, price, total, link, note
        )
        await s.commit()
        oid = order.id

    await state.clear()

    # ارسال به گروه
    group_msg_id = None
    if group_id:
        try:
            from datetime import datetime
            gtext = (
                f"🆕 <b>سفارش جدید #{oid}</b>\n{'━'*28}\n"
                f"👤 کاربر: @{db_user.username or 'بدون یوزر'} (ID: <code>{db_user.telegram_id}</code>)\n"
                f"🎛 پنل: <b>{panel_name}</b>\n"
                f"📌 خدمت: <b>{svc_name[:50]}</b>\n"
                f"🔗 لینک: <code>{link}</code>\n"
                f"🔢 تعداد: <b>{qty:,}</b>\n"
                + (f"📝 توضیح: <i>{note}</i>\n" if note else "") +
                f"💰 مبلغ: <b>${total:.4f}</b>\n"
                f"⏰ زمان: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"{'━'*28}\n"
                f"وضعیت: ⏳ در انتظار\n\n"
                f"<i>ریپلی کنید: صف | انجام | تکمیل | رد | partial</i>"
            )
            sent = await bot.send_message(group_id, gtext, parse_mode="HTML")
            group_msg_id = sent.message_id
            async with AsyncSessionLocal() as s2:
                from sqlalchemy import update as _upd
                from db.models import PanelOrder
                await s2.execute(_upd(PanelOrder).where(PanelOrder.id == oid)
                                 .values(group_message_id=group_msg_id))
                await s2.commit()
        except Exception as e:
            logger.warning(f"group notify failed: {e}")

    # نوتیف کسر موجودی
    new_bal = bal - total
    await notify_balance_deducted(bot, db_user.telegram_id, total,
                                   f"سفارش #{oid} — {svc_name[:30]}", new_bal)

    await cb.message.edit_text(
        f"✅ <b>سفارش ثبت شد!</b>\n{'━'*28}\n"
        f"🆔 شناسه: <b>#{oid}</b>\n"
        f"📌 خدمت: <b>{svc_name[:45]}</b>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        f"💰 پرداخت: <b>${total:.4f}</b>\n"
        f"{'━'*28}\n\n"
        "⏳ سفارش شما در صف بررسی است.\n"
        "پس از تغییر وضعیت به شما اطلاع داده می‌شود.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 سفارشات من", callback_data="user_orders")],
            [InlineKeyboardButton(text="🏠 خانه",        callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )
