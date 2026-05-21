"""Panel User Handler — i18n v5.1"""
from html import escape
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import User, PanelCategory
from services.panel_service import (
    get_panel, get_categories, get_services, get_service, create_panel_order
)
from services.user_service import get_user_by_telegram_id, deduct_balance
from services.notification_service import notify_order_placed, notify_group_new_order
from i18n import t
router = Router()

class PanelUserState(StatesGroup):
    order_link = State()
    order_qty  = State()
    order_note = State()

def _kb(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def _back(cb, lang="en"): return _kb([InlineKeyboardButton(text=t("btn_back",lang), callback_data=cb)])
def _cancel(cb="user_home", lang="en"): return _kb([InlineKeyboardButton(text=t("btn_cancel",lang), callback_data=cb)])

async def _get_cat(session, cat_id: int):
    result = await session.execute(select(PanelCategory).where(PanelCategory.id == cat_id))
    return result.scalar_one_or_none()

@router.callback_query(F.data.regexp(r"^panel_user_\d+$"))
async def panel_user_cats(cb: CallbackQuery, db_user: User = None, user_lang: str = "en"):
    await cb.answer()
    lang = getattr(db_user,"language",None) or user_lang or "en"
    pid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        panel = await get_panel(s, pid)
        if not panel or not panel.is_active:
            await cb.message.edit_text(t("panel_unavailable",lang), reply_markup=_back("user_home",lang)); return
        cats = await get_categories(s, pid, active_only=True)
    desc = f"\n<i>{escape(panel.description)}</i>" if panel.description else ""
    rows = [[InlineKeyboardButton(text=f"{c.icon or ''} {escape(c.name)}".strip(), callback_data=f"panel_cat_{c.id}_{pid}")] for c in cats]
    rows.append([InlineKeyboardButton(text=t("btn_home",lang), callback_data="user_home")])
    await cb.message.edit_text(f"<b>{escape(panel.button_label or panel.name)}</b>\n{'━'*28}{desc}\n\n{t('choose_category',lang)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@router.callback_query(F.data.regexp(r"^panel_cat_\d+_\d+$"))
async def panel_user_svcs(cb: CallbackQuery, db_user: User = None, user_lang: str = "en"):
    await cb.answer()
    lang = getattr(db_user,"language",None) or user_lang or "en"
    _, _, cid, pid = cb.data.split("_"); cid, pid = int(cid), int(pid)
    async with AsyncSessionLocal() as s:
        cat  = await _get_cat(s, cid)
        svcs = await get_services(s, cid, active_only=True)
    if not cat:
        await cb.message.edit_text(t("cat_not_found",lang), reply_markup=_back(f"panel_user_{pid}",lang)); return
    rows = [[InlineKeyboardButton(text=f"📌 {escape(sv.name)} — ${sv.price:.2f}", callback_data=f"panel_svc_{sv.id}_{pid}")] for sv in svcs]
    rows.append([InlineKeyboardButton(text=t("btn_back",lang), callback_data=f"panel_user_{pid}")])
    await cb.message.edit_text(f"{cat.icon or ''} <b>{escape(cat.name)}</b>\n{'━'*28}\n\n{t('choose_service',lang)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@router.callback_query(F.data.regexp(r"^panel_svc_\d+_\d+$"))
async def panel_user_svc_detail(cb: CallbackQuery, state: FSMContext, db_user: User = None, user_lang: str = "en"):
    await cb.answer()
    lang = getattr(db_user,"language",None) or user_lang or "en"
    _, _, sid, pid = cb.data.split("_"); sid, pid = int(sid), int(pid)
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
        bal = float(db_user.balance or 0) if db_user else 0.0
    if not svc or not svc.is_active:
        await cb.message.edit_text(t("svc_not_found",lang), reply_markup=_back(f"panel_user_{pid}",lang)); return
    desc_line = f"\n📄 {escape(svc.description)}" if svc.description else ""
    text = (f"📌 <b>{escape(svc.name)}</b>\n{'━'*28}{desc_line}\n"
            f"💰 {t('order_cost',lang)}: <b>${svc.price:.4f}</b>\n"
            f"{t('smm_min_max',lang,mn=svc.min_qty,mx=svc.max_qty)}\n"
            f"{t('smm_your_balance',lang,bal=f'{bal:.2f}')}")
    rows = [
        [InlineKeyboardButton(text=t("btn_new_order",lang), callback_data=f"panel_order_start_{sid}_{pid}")],
        [InlineKeyboardButton(text=t("btn_back",lang), callback_data=f"panel_cat_{svc.category_id}_{pid}")]
    ]
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@router.callback_query(F.data.regexp(r"^panel_order_start_\d+_\d+$"))
async def panel_order_start(cb: CallbackQuery, state: FSMContext, db_user: User = None, user_lang: str = "en"):
    await cb.answer()
    lang = getattr(db_user,"language",None) or user_lang or "en"
    _, _, _, sid, pid = cb.data.split("_"); sid, pid = int(sid), int(pid)
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
    if not svc or not svc.is_active:
        await cb.message.edit_text(t("svc_unavailable",lang), reply_markup=_back("user_home",lang)); return
    await state.set_state(PanelUserState.order_link)
    await state.update_data(svc_id=sid, panel_id=pid, lang=lang)
    await cb.message.edit_text(f"🛒 <b>{escape(svc.name)}</b>\n{'━'*28}\n\n{t('enter_link',lang)}", reply_markup=_cancel(f"panel_user_{pid}",lang), parse_mode="HTML")

@router.message(PanelUserState.order_link)
async def panel_order_link(msg: Message, state: FSMContext, db_user: User = None, user_lang: str = "en"):
    lang = getattr(db_user,"language",None) or user_lang or "en"
    data = await state.get_data(); pid = data.get("panel_id",0)
    link = (msg.text or "").strip()
    if not link:
        await msg.answer(t("link_empty",lang), reply_markup=_cancel(f"panel_user_{pid}",lang)); return
    await state.update_data(link=link)
    await state.set_state(PanelUserState.order_qty)
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, data["svc_id"])
    await msg.answer(t("enter_qty",lang,mn=svc.min_qty,mx=svc.max_qty), reply_markup=_cancel(f"panel_user_{pid}",lang), parse_mode="HTML")

@router.message(PanelUserState.order_qty)
async def panel_order_qty(msg: Message, state: FSMContext, db_user: User = None, user_lang: str = "en"):
    lang = getattr(db_user,"language",None) or user_lang or "en"
    data = await state.get_data(); pid = data.get("panel_id",0)
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, data["svc_id"])
    mn, mx = svc.min_qty, svc.max_qty
    try:
        qty = int((msg.text or "").strip().replace(",","").replace("٬",""))
        if qty <= 0: raise ValueError
    except (ValueError, TypeError):
        await msg.answer(t("qty_invalid",lang), reply_markup=_cancel(f"panel_user_{pid}",lang)); return
    if not (mn <= qty <= mx):
        await msg.answer(t("qty_range",lang,mn=mn,mx=mx), reply_markup=_cancel(f"panel_user_{pid}",lang), parse_mode="HTML"); return
    await state.update_data(qty=qty)
    await state.set_state(PanelUserState.order_note)
    await msg.answer(t("enter_note",lang), reply_markup=_cancel(f"panel_user_{pid}",lang), parse_mode="HTML")

@router.message(PanelUserState.order_note)
async def panel_order_note(msg: Message, state: FSMContext, db_user: User = None, user_lang: str = "en"):
    lang = getattr(db_user,"language",None) or user_lang or "en"
    data = await state.get_data(); pid = data.get("panel_id",0)
    note = "" if (msg.text or "").strip() in ("/skip","skip") else (msg.text or "").strip()
    await state.update_data(note=note)
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, data["svc_id"])
        bal = float(db_user.balance or 0) if db_user else 0.0
    qty = data["qty"]; link = data["link"]; total = round(svc.price * qty, 4)
    bal_ok = bal >= total; sep = "━" * 28
    text = (
        f"{t('order_confirm_title',lang)}\n{sep}\n"
        f"{t('order_panel',lang)}: <b>{escape(svc.name[:50])}</b>\n"
        f"{t('order_link_lbl',lang)}: <code>{escape(link)}</code>\n"
        f"{t('order_qty_lbl',lang)}: <b>{qty:,}</b>\n"
        + (f"{t('order_note_lbl',lang)}: <i>{escape(note)}</i>\n" if note else "")
        + f"{sep}\n{t('order_cost',lang)}: <b>${total:.4f}</b>\n"
        f"💳 {t('balance_label',lang)}: <b>${bal:.2f}</b>\n\n"
        + (t("order_bal_ok",lang) if bal_ok else t("order_bal_low",lang))
    )
    rows = []
    if bal_ok: rows.append([InlineKeyboardButton(text=t("btn_confirm",lang), callback_data="panel_confirm")])
    else:      rows.append([InlineKeyboardButton(text=t("btn_charge",lang),  callback_data="user_deposit")])
    rows.append([InlineKeyboardButton(text=t("btn_cancel",lang), callback_data=f"panel_user_{pid}")])
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@router.callback_query(F.data == "panel_confirm")
async def panel_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot, db_user: User = None, user_lang: str = "en"):
    lang = getattr(db_user,"language",None) or user_lang or "en"
    data = await state.get_data()
    if not data.get("svc_id"):
        await cb.message.edit_text(t("order_info_missing",lang), reply_markup=_back("user_home",lang)); return
    await cb.answer()
    await cb.message.edit_text(t("placing_order",lang), parse_mode="HTML")
    async with AsyncSessionLocal() as s:
        user  = await get_user_by_telegram_id(s, cb.from_user.id)
        if not user:
            await cb.message.edit_text(t("user_not_found",lang), reply_markup=_back("user_home",lang)); return
        svc   = await get_service(s, data["svc_id"])
        panel = await get_panel(s, data["panel_id"])
        if not svc or not svc.is_active:
            await cb.message.edit_text(t("svc_unavailable",lang), reply_markup=_back("user_home",lang)); return
        if not panel or not panel.is_active:
            await cb.message.edit_text(t("panel_gone",lang), reply_markup=_back("user_home",lang)); return
        qty = data["qty"]; link = data["link"]; note = data.get("note","")
        total = round(svc.price * qty, 4); bal = float(user.balance or 0)
        if bal < total:
            await cb.message.edit_text(t("insufficient_balance",lang), reply_markup=_kb(
                [InlineKeyboardButton(text=t("btn_charge",lang), callback_data="user_deposit")],
                [InlineKeyboardButton(text=t("btn_home",lang),   callback_data="user_home")]
            )); return
        ok, new_bal = await deduct_balance(s, user.id, total)
        if not ok:
            await cb.message.edit_text(t("order_deduct_error",lang), reply_markup=_back("user_home",lang)); return
        cat      = await _get_cat(s, svc.category_id)
        cat_name = cat.name if cat else "—"
        order = await create_panel_order(
            s, user_id=user.id, panel_id=panel.id, service_id=svc.id,
            link=link, quantity=qty, amount=total, note=note
        )
        await s.commit(); oid = order.id
    await state.clear()
    sep = "━" * 28
    await cb.message.edit_text(
        f"{t('order_confirmed',lang)}\n{sep}\n"
        f"{t('order_panel',lang)}: <b>{escape(panel.name)}</b>\n"
        f"{t('order_cat',lang)}: <b>{escape(cat_name)}</b>\n"
        f"{t('order_service',lang)}: <b>{escape(svc.name[:50])}</b>\n"
        f"{t('order_qty_lbl',lang)}: <b>{qty:,}</b>\n"
        f"{t('order_paid',lang)}: <b>${total:.4f}</b>\n"
        f"{t('order_bal_after',lang)}: <b>${new_bal:.2f}</b>\n\n"
        f"{t('order_waiting',lang)}",
        reply_markup=_kb(
            [InlineKeyboardButton(text=t("btn_my_orders",lang), callback_data="user_orders")],
            [InlineKeyboardButton(text=t("btn_home",lang),      callback_data="user_home")]
        ), parse_mode="HTML"
    )
    try: await notify_order_placed(bot, user.telegram_id, oid, panel.name, cat_name, svc.name, qty, total, new_bal, lang=lang)
    except Exception: pass
    try: await notify_group_new_order(bot, oid, panel, cat_name, svc.name, user, link, qty, total, note)
    except Exception: pass