"""
Panel User Handler
"""
from i18n import t
import logging
from html import escape
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User, Transaction
from services.panel_service import get_panel, get_categories, get_services, get_service, create_panel_order
from services.notification_service import notify_order_confirmed
from sqlalchemy import select, update as _upd

logger = logging.getLogger("panel_user")
router = Router()

class PanelUserState(StatesGroup):
    order_link = State()
    order_qty  = State()
    order_note = State()

def _back(cb, lang="en"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("btn_back", lang), callback_data=cb)]])
def _cancel(cb="user_home", lang="en"): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("btn_cancel", lang), callback_data=cb)]])

@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery): await cb.answer()


# ── لیست دسته‌بندی‌های پنل ───────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_user_\d+$"))
async def panel_user_cats(cb: CallbackQuery, user_lang: str = "en"):
    lang = getattr(db_user, "language", None) or user_lang or "en"
    await cb.answer()
    pid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        panel = await get_panel(s, pid)
        cats  = await get_categories(s, pid, active_only=True)
    if not panel or not panel.is_active:
        await cb.message.edit_text(t("panel_unavailable", lang), reply_markup=_back("user_home")); return
    rows = [[InlineKeyboardButton(text=f"{c.icon} {escape(c.name)}", callback_data=f"panel_cat_{c.id}_{pid}")] for c in cats]
    rows.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])
    desc = f"\n<i>{escape(panel.description)}</i>" if panel.description else ""
    await cb.message.edit_text(
        f"<b>{escape(panel.button_label)}</b>\n{'━'*28}{desc}\n\nیک دسته‌بندی را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


# ── لیست خدمات دسته ───────────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_cat_\d+_\d+$"))
async def panel_user_svcs(cb: CallbackQuery, user_lang: str = "en"):
    lang = getattr(db_user, "language", None) or user_lang or "en"
    await cb.answer()
    parts = cb.data.split("_"); cid, pid = int(parts[2]), int(parts[3])
    from db.models import PanelCategory
    async with AsyncSessionLocal() as s:
        res  = await s.execute(select(PanelCategory).where(PanelCategory.id == cid))
        cat  = res.scalar_one_or_none()
        svcs = await get_services(s, cid, active_only=True)
    if not cat:
        await cb.message.edit_text("❌ دسته یافت نشد.", reply_markup=_back(f"panel_user_{pid}")); return
    rows = [[InlineKeyboardButton(text=f"📌 {escape(sv.name)} — ${sv.price:.2f}/واحد", callback_data=f"panel_svc_{sv.id}_{pid}")] for sv in svcs]
    rows.append([InlineKeyboardButton(text=t("btn_back", lang), callback_data=f"panel_user_{pid}")])
    await cb.message.edit_text(
        f"{cat.icon} <b>{escape(cat.name)}</b>\n{'━'*28}\n\nیک خدمت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


# ── جزئیات خدمت ────────────────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_svc_\d+_\d+$"))
async def panel_user_svc_detail(cb: CallbackQuery, state: FSMContext, db_user: User = None, user_lang: str = "en"):
    lang = getattr(db_user, "language", None) or user_lang or "en"
    await cb.answer()
    parts = cb.data.split("_"); sid, pid = int(parts[2]), int(parts[3])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
    if not svc or not svc.is_active:
        await cb.message.edit_text("❌ این خدمت در دسترس نیست.", reply_markup=_back(f"panel_user_{pid}")); return
    bal = float(db_user.balance or 0) if db_user else 0
    await state.update_data(pu_svc_id=sid, pu_panel_id=pid, pu_svc_name=svc.name,
                            pu_price=svc.price, pu_min=svc.min_qty, pu_max=svc.max_qty, pu_cat_id=svc.category_id)
    await cb.message.edit_text(
        f"📌 <b>{escape(svc.name)}</b>\n{'━'*28}\n"
        + (f"📄 {escape(svc.description)}\n" if svc.description else "") +
        f"💰 قیمت: <b>${svc.price:.4f}</b> / واحد\n"
        f"📊 حداقل: <b>{svc.min_qty:,}</b> | حداکثر: <b>{svc.max_qty:,}</b>\n"
        f"💳 موجودی شما: <b>${bal:.2f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش دهید", callback_data=f"panel_order_start_{sid}_{pid}")],
            [InlineKeyboardButton(text=t("btn_back", lang),      callback_data=f"panel_cat_{svc.category_id}_{pid}")],
        ]), parse_mode="HTML"
    )


# ── شروع سفارش ─────────────────────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^panel_order_start_\d+_\d+$"))
async def panel_order_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split("_"); sid, pid = int(parts[3]), int(parts[4])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
    if not svc or not svc.is_active:
        await cb.message.edit_text("❌ این خدمت در دسترس نیست.", reply_markup=_back(f"panel_user_{pid}")); return
    await state.update_data(pu_svc_id=sid, pu_panel_id=pid, pu_svc_name=svc.name,
                            pu_price=svc.price, pu_min=svc.min_qty, pu_max=svc.max_qty, pu_cat_id=svc.category_id)
    await state.set_state(PanelUserState.order_link)
    await cb.message.edit_text(
        f"🛒 <b>{escape(svc.name)}</b>\n{'━'*28}\n\n"
        "🔗 <b>لینک یا یوزرنیم مقصد را وارد کنید:</b>\n"
        "<i>مثال: https://t.me/channel یا @username</i>",
        reply_markup=_cancel(f"panel_svc_{sid}_{pid}"), parse_mode="HTML"
    )


@router.message(PanelUserState.order_link)
async def panel_order_link(msg: Message, state: FSMContext):
    link = (msg.text or "").strip()
    if not link or link.startswith("/"):
        await msg.answer("❌ لینک نمی‌تواند خالی باشد.", reply_markup=_cancel()); return
    await state.update_data(pu_link=link)
    await state.set_state(PanelUserState.order_qty)
    data = await state.get_data()
    mn, mx, price = data.get("pu_min",1), data.get("pu_max",10000), data.get("pu_price",0)
    await msg.answer(
        f"🔢 <b>تعداد را وارد کنید:</b>\n{'━'*28}\n\n"
        f"📊 حداقل: <b>{mn:,}</b> | حداکثر: <b>{mx:,}</b>\n"
        f"💰 قیمت: <b>${price:.4f}</b> / واحد\n\n<i>فقط عدد — مثال: 1000</i>",
        reply_markup=_cancel(), parse_mode="HTML"
    )


@router.message(PanelUserState.order_qty)
async def panel_order_qty(msg: Message, state: FSMContext, db_user: User = None):
    try:
        qty = int((msg.text or "").strip().replace(",","").replace("٬",""))
        if qty <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح مثبت وارد کنید.", reply_markup=_cancel()); return
    data = await state.get_data()
    mn, mx = data.get("pu_min",1), data.get("pu_max",10000)
    if qty < mn or qty > mx:
        await msg.answer(f"❌ تعداد باید بین <b>{mn:,}</b> و <b>{mx:,}</b> باشد.", reply_markup=_cancel(), parse_mode="HTML"); return
    await state.update_data(pu_qty=qty)
    await state.set_state(PanelUserState.order_note)
    await msg.answer("📝 <b>توضیح اضافه (اختیاری):</b>\n<i>برای رد کردن /skip بزنید</i>",
                     reply_markup=_cancel(), parse_mode="HTML")


@router.message(PanelUserState.order_note)
async def panel_order_note(msg: Message, state: FSMContext, db_user: User = None):
    note  = "" if (msg.text or "").strip() in ("/skip","skip") else (msg.text or "").strip()
    await state.update_data(pu_note=note)
    data  = await state.get_data()
    qty   = data.get("pu_qty", 1)
    price = data.get("pu_price", 0.0)
    total = round(price * qty, 6)
    bal   = float(db_user.balance or 0) if db_user else 0
    bal_ok = (bal + 1e-9) >= total
    svc_name = data.get("pu_svc_name", "")
    link     = data.get("pu_link", "")
    text = (
        f"📋 <b>تایید سفارش</b>\n{'━'*28}\n"
        f"📌 خدمت: <b>{escape(svc_name[:50])}</b>\n"
        f"🔗 لینک: <code>{escape(link)}</code>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        + (f"📝 توضیح: <i>{escape(note)}</i>\n" if note else "") +
        f"{'━'*28}\n💰 هزینه: <b>${total:.4f}</b>\n💳 موجودی: <b>${bal:.2f}</b>\n\n"
    )
    text += "✅ موجودی کافی است." if bal_ok else "❌ موجودی ناکافی."
    rows = []
    if bal_ok: rows.append([InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="panel_confirm")])
    else:      rows.append([InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")])
    rows.append([InlineKeyboardButton(text=t("btn_cancel", lang), callback_data="user_home")])
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


# ── تایید و ثبت سفارش — atomic transaction ───────────────────────────────────────────────────────────────
@router.callback_query(F.data == "panel_confirm")
async def panel_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot, db_user: User = None):
    await cb.answer()
    data     = await state.get_data()
    svc_id   = data.get("pu_svc_id")
    panel_id = data.get("pu_panel_id")
    svc_name = data.get("pu_svc_name", "")
    qty      = data.get("pu_qty", 1)
    price    = data.get("pu_price", 0.0)
    link     = data.get("pu_link", "")
    note     = data.get("pu_note", "")
    total    = round(price * qty, 6)
    if not svc_id or not panel_id:
        await cb.message.edit_text("❌ خطا: اطلاعات سفارش ناقص است.", reply_markup=_back("user_home"))
        await state.clear(); return
    await state.clear()
    await cb.message.edit_text("⏳ <b>در حال ثبت سفارش...</b>", parse_mode="HTML")
    async with AsyncSessionLocal() as s:
        from db.models import User as _U, Panel as _P
        ur = await s.execute(select(_U).where(_U.id == db_user.id))
        user = ur.scalar_one_or_none()
        if not user:
            await cb.message.edit_text("❌ کاربر یافت نشد.", reply_markup=_back("user_home")); return
        bal = float(user.balance or 0)
        if (bal + 1e-9) < total:
            await cb.message.edit_text(
                f"❌ <b>موجودی ناکافی</b>\n\n💰 هزینه: <b>${total:.4f}</b>\n💳 موجودی: <b>${bal:.2f}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")],
                    [InlineKeyboardButton(text="🏠 بازگشت",       callback_data="user_home")],
                ]), parse_mode="HTML"
            ); return
        svc = await get_service(s, svc_id)
        if not svc or not svc.is_active:
            await cb.message.edit_text("❌ این خدمت دیگر در دسترس نیست.", reply_markup=_back("user_home")); return
        pr = await s.execute(select(_P).where(_P.id == panel_id))
        panel = pr.scalar_one_or_none()
        if not panel or not panel.is_active:
            await cb.message.edit_text("❌ این پنل دیگر در دسترس نیست.", reply_markup=_back("user_home")); return
        from db.models import PanelCategory as _PC
        _cr  = await s.execute(select(_PC).where(_PC.id == svc.category_id))
        _cat = _cr.scalar_one_or_none()
        cat_name = _cat.name if _cat else "—"
        user.balance = round(bal - total, 6)
        s.add(Transaction(user_id=user.id, type="order", amount=-total,
                          status="completed", method="panel",
                          description=f"سفارش پنل — {svc_name[:50]}"))
        order = await create_panel_order(
            s, user_id=user.id, panel_id=panel_id, service_id=svc_id,
            service_name=svc_name, panel_name=panel.name,
            quantity=qty, unit_price=price, total_price=total,
            link=link, note=note,
        )
        oid     = order.id
        new_bal = float(user.balance)
        grp_msg_id = None
        if panel.group_chat_id:
            try:
                parts_n = [p for p in [user.first_name, user.last_name] if p]
                display = " ".join(parts_n) if parts_n else (user.username or str(user.telegram_id))
                sent = await bot.send_message(
                    panel.group_chat_id,
                    "🆕 <b>سفارش #" + str(oid) + "</b>\n"
                    + "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    + "🏷 پنل: <b>" + escape(panel.name) + "</b>\n"
                    + "📂 دسته: <b>" + escape(cat_name) + "</b>\n"
                    + "📌 خدمت: <b>" + escape(svc_name[:50]) + "</b>\n"
                    + "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    + "👤 کاربر: <code>" + str(user.telegram_id) + "</code>"
                    + (" (@" + escape(user.username) + ")" if user.username else "") + "\n"
                    + "🔗 لینک: <code>" + escape(link[:100]) + "</code>\n"
                    + "🔢 تعداد: <b>" + f"{qty:,}" + "</b>\n"
                    + "💰 مبلغ: <b>$" + f"{total:.4f}" + "</b>\n"
                    + ("📝 توضیح: <i>" + escape(note) + "</i>\n" if note else "")
                    + "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏳ وضعیت: <b>در انتظار</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="🔄 در انجام", callback_data=f"adm_grp_porder_{oid}_{panel_id}_processing"),
                            InlineKeyboardButton(text="✅ تکمیل",    callback_data=f"adm_grp_porder_{oid}_{panel_id}_completed"),
                        ],
                        [
                            InlineKeyboardButton(text="⚠️ جزئی",    callback_data=f"adm_grp_porder_{oid}_{panel_id}_partial"),
                            InlineKeyboardButton(text="❌ رد",       callback_data=f"adm_grp_porder_{oid}_{panel_id}_rejected"),
                        ],
                    ])
                )
                grp_msg_id = sent.message_id
            except Exception as eg:
                logger.warning(f"Cannot send to panel group {panel.group_chat_id}: {eg}")
        if grp_msg_id:
            from db.models import PanelOrder as _PO
            await s.execute(_upd(_PO).where(_PO.id == oid).values(group_message_id=grp_msg_id))
        await s.commit()
    await cb.message.edit_text(
        f"✅ <b>سفارش ثبت شد!</b>\n{chr(9473)*28}\n"
        f"🏷 پنل: <b>{escape(panel.name)}</b>\n"
        f"📂 دسته: <b>{escape(cat_name)}</b>\n"
        f"📌 خدمت: <b>{escape(svc_name[:50])}</b>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        f"💰 پرداخت: <b>${total:.4f}</b>\n"
        f"💳 موجودی باقی‌مانده: <b>${new_bal:.2f}</b>\n\n"
        "⏳ سفارش شما در صف بررسی است.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 سفارشات من", callback_data="user_orders")],
            [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_home")],
        ]), parse_mode="HTML"
    )
    try:
        await notify_order_confirmed(bot, db_user.telegram_id,
            order_id=oid, panel_name=panel.name, cat_name=cat_name,
            service_name=svc_name, quantity=qty, amount=total, balance=new_bal)
    except Exception: pass
