"""
SMMPass SMM Panel handler.
Features:
- موجودی حساب (USD)
- لیست سرویس‌ها با فیلتر دسته + جستجو
- ثبت سفارش عادی + Drip-feed
- وضعیت سفارش تکی + باچ چند سفارش
- Refill سفارش
- به‌روزرسانی سرویس‌ها real-time
"""
import logging
import os

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger   = logging.getLogger("smmpass")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PAGE_SIZE = 8


# ─── FSM ────────────────────────────────────────────────────────────────────
class SMPState(StatesGroup):
    search_query    = State()
    order_link      = State()
    order_quantity  = State()
    order_runs      = State()   # drip-feed
    order_interval  = State()   # drip-feed
    order_status    = State()
    batch_status    = State()
    refill_order    = State()


# ─── Helpers ────────────────────────────────────────────────────────────────
def _icon(status: str) -> str:
    s = status.lower()
    if any(x in s for x in ("complet", "done", "finish")): return "\u2705"
    if any(x in s for x in ("pending",)):                   return "\u23f3"
    if any(x in s for x in ("progress", "processing", "active")): return "\U0001f504"
    if any(x in s for x in ("cancel", "fail", "error", "refund")): return "\u274c"
    if "partial" in s: return "\u26a0\ufe0f"
    return "\U0001f7e1"


def _type_icon(t: str) -> str:
    t = t.lower()
    if "drip" in t or "subscription" in t: return "\U0001f4c6"
    if "package" in t:   return "\U0001f4e6"
    if "comment" in t:   return "\U0001f4ac"
    if "mention" in t:   return "\U0001f4e2"
    return "\U0001f539"


# ─── Keyboards ──────────────────────────────────────────────────────────────
def smp_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4b0 \u0645\u0648\u062c\u0648\u062f\u06cc \u062d\u0633\u0627\u0628 (USD)",    callback_data="smp_balance")],
        [InlineKeyboardButton(text="\U0001f4cb \u0644\u06cc\u0633\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",         callback_data="smp_services_0")],
        [InlineKeyboardButton(text="\U0001f504 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",  callback_data="smp_refresh")],
        [InlineKeyboardButton(text="\U0001f50d \u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",   callback_data="smp_search")],
        [InlineKeyboardButton(text="\u2795 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u062c\u062f\u06cc\u062f",       callback_data="smp_new_order")],
        [InlineKeyboardButton(text="\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634",          callback_data="smp_order_status")],
        [InlineKeyboardButton(text="\U0001f4ca \u0648\u0636\u0639\u06cc\u062a \u0686\u0646\u062f \u0633\u0641\u0627\u0631\u0634",     callback_data="smp_batch_status")],
        [InlineKeyboardButton(text="\U0001f504 \u0631\u06cc\u0641\u06cc\u0644 \u0633\u0641\u0627\u0631\u0634",            callback_data="smp_refill")],
        [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",                callback_data="menu_main")],
    ])


def _svc_kb(services: list, page: int) -> InlineKeyboardMarkup:
    total = len(services)
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    rows  = []
    for s in services[start:end]:
        df   = " \U0001f4c6" if s["dripfeed"] else ""
        icon = _type_icon(s["type"])
        rows.append([InlineKeyboardButton(
            text=f"{icon} [{s['service']}] {s['name'][:26]}{df} | ${s['rate']}",
            callback_data=f"smp_svc_{s['service']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05\ufe0f", callback_data=f"smp_services_{page-1}"))
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="smp_noop"))
    if end < total:
        nav.append(InlineKeyboardButton(text="\u27a1\ufe0f", callback_data=f"smp_services_{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="smp_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Entry ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_smmpass")
async def smp_entry(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "\U0001f680 <b>SMMPass \u2014 \u067e\u0646\u0644 SMM</b>\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=smp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "smp_menu")
async def smp_menu_back(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "\U0001f680 <b>SMMPass \u2014 \u067e\u0646\u0644 SMM</b>\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=smp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "smp_noop")
async def smp_noop(cb: CallbackQuery):
    await cb.answer()


# ─── Balance ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_balance")
async def smp_balance(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    msg = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0645\u0648\u062c\u0648\u062f\u06cc...", parse_mode="HTML")
    try:
        from services.smmpass import get_balance
        d = await get_balance()
        try: bal = f"{float(d['balance']):,.4f}"
        except: bal = d['balance']
        await msg.edit_text(
            f"\U0001f4b0 <b>\u0645\u0648\u062c\u0648\u062f\u06cc SMMPass</b>\n\n"
            f"\U0001f4b5 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal}</b> {d['currency']}",
            reply_markup=smp_main_menu(), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                            reply_markup=smp_main_menu(), parse_mode="HTML")


# ─── Services ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_refresh")
async def smp_refresh(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc...")
    msg = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 \u0627\u0632 \u0633\u0627\u06cc\u062a...", parse_mode="HTML")
    try:
        from services.smmpass import get_services
        svcs = await get_services(force=True)
        await msg.edit_text(
            f"\u2705 <b>{len(svcs)}</b> \u0633\u0631\u0648\u06cc\u0633 \u0628\u0647\u200c\u0631\u0648\u0632 \u0634\u062f.",
            reply_markup=smp_main_menu(), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                            reply_markup=smp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("smp_services_"))
async def smp_services(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    data = await state.get_data()
    cat  = data.get("smp_cat", "")
    msg  = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc...", parse_mode="HTML")
    try:
        from services.smmpass import get_services
        all_svcs = await get_services()
        if not all_svcs:
            await msg.edit_text("\u274c \u0633\u0631\u0648\u06cc\u0633\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f. \u0627\u0628\u062a\u062f\u0627 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u06a9\u0646\u06cc\u062f.",
                                reply_markup=smp_main_menu(), parse_mode="HTML"); return

        svcs = [s for s in all_svcs if not cat or s["category"] == cat]
        cats = list(dict.fromkeys(s["category"] for s in all_svcs))

        cat_rows = []
        for i in range(0, len(cats), 2):
            row = []
            for c in cats[i:i+2]:
                active = "\u2705 " if c == cat else ""
                row.append(InlineKeyboardButton(
                    text=f"{active}{c[:22]}",
                    callback_data=f"smp_cat_{c[:30]}"
                ))
            cat_rows.append(row)
        if cat:
            cat_rows.append([InlineKeyboardButton(
                text="\u274c \u062d\u0630\u0641 \u0641\u06cc\u0644\u062a\u0631",
                callback_data="smp_cat_CLEAR"
            )])

        svc_kb   = _svc_kb(svcs, page)
        all_rows = cat_rows + svc_kb.inline_keyboard
        kb       = InlineKeyboardMarkup(inline_keyboard=all_rows)

        header = f"\U0001f4cc \u062f\u0633\u062a\u0647: <b>{cat}</b>\n" if cat else ""
        await msg.edit_text(
            f"\U0001f4ca <b>\u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 ({len(svcs)} \u0645\u0648\u0631\u062f)</b>\n{header}"
            "\U0001f4c6 = Drip-feed | \U0001f4ac = Custom Comments\n"
            "\u0631\u0648\u06cc \u0633\u0631\u0648\u06cc\u0633 \u0628\u0632\u0646\u06cc\u062f \u062a\u0627 \u062c\u0632\u0626\u06cc\u0627\u062a \u0628\u0628\u06cc\u0646\u06cc\u062f:",
            reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                            reply_markup=smp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("smp_cat_"))
async def smp_cat(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cat = cb.data[8:]
    await state.update_data(smp_cat="" if cat == "CLEAR" else cat)
    cb.data = "smp_services_0"
    await smp_services(cb, state)


@router.callback_query(F.data.startswith("smp_svc_"))
async def smp_svc_detail(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        svc  = next((s for s in svcs if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("\u274c \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True); return

        df_line = "\U0001f4c6 <b>Drip-feed \u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc \u0645\u06cc\u200c\u0634\u0648\u062f</b>\n" if svc["dripfeed"] else ""
        desc_line = f"\U0001f4dd \u062a\u0648\u0636\u06cc\u062d: <i>{svc['desc']}</i>\n" if svc["desc"] else ""
        text = (
            f"{_type_icon(svc['type'])} <b>{svc['name']}</b>\n\n"
            f"\U0001f3f7 \u062f\u0633\u062a\u0647: <code>{svc['category']}</code>\n"
            f"\U0001f522 \u0634\u0646\u0627\u0633\u0647: <code>{svc['service']}</code>\n"
            f"\U0001f4b0 \u0646\u0631\u062e: <b>${svc['rate']}</b> / 1000\n"
            f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: <b>{svc['min']}</b>\n"
            f"\U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{svc['max']}</b>\n"
            f"\U0001f4cc \u0646\u0648\u0639: <code>{svc['type']}</code>\n"
            f"{df_line}{desc_line}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"\u2795 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 [{svc_id}]",
                callback_data=f"smp_order_svc_{svc_id}"
            )],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",
                                  callback_data="smp_services_0")],
        ])
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"\u274c {str(e)[:60]}", show_alert=True)


# ─── Search ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_search")
async def smp_search_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SMPState.search_query)
    await cb.message.edit_text(
        "\U0001f50d <b>\u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627</b>\n\n"
        "\u0646\u0627\u0645 \u0633\u0631\u0648\u06cc\u0633 / \u062f\u0633\u062a\u0647 / \u0634\u0646\u0627\u0633\u0647 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: instagram followers, 5</i>",
        parse_mode="HTML")


@router.message(SMPState.search_query)
async def smp_search_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    q = (msg.text or "").strip().lower()
    await state.clear()
    try:
        from services.smmpass import get_services
        svcs    = await get_services()
        results = [s for s in svcs
                   if q in s["name"].lower()
                   or q in s["category"].lower()
                   or q == str(s["service"])]
        if not results:
            await msg.answer(f"\u274c \u0646\u062a\u06cc\u062c\u0647\u200c\u0627\u06cc \u0628\u0631\u0627\u06cc '<b>{q}</b>' \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.",
                             reply_markup=smp_main_menu(), parse_mode="HTML"); return
        rows = []
        for s in results[:20]:
            df = " \U0001f4c6" if s["dripfeed"] else ""
            rows.append([InlineKeyboardButton(
                text=f"{_type_icon(s['type'])} [{s['service']}] {s['name'][:26]}{df} | ${s['rate']}",
                callback_data=f"smp_svc_{s['service']}"
            )])
        rows.append([InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",
                                          callback_data="smp_menu")])
        suffix = " (\u0627\u0648\u0644 20)" if len(results) > 20 else ""
        await msg.answer(
            f"\U0001f50d '<b>{q}</b>': <b>{len(results)}</b> \u0645\u0648\u0631\u062f{suffix}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"\u274c <code>{str(e)[:120]}</code>",
                         reply_markup=smp_main_menu(), parse_mode="HTML")


# ─── New Order ───────────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_new_order")
async def smp_new_order(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SMPState.search_query)
    await state.update_data(smp_order_mode=True)
    await cb.message.edit_text(
        "\u2795 <b>\u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u062c\u062f\u06cc\u062f</b>\n\n"
        "\u0646\u0627\u0645 \u06cc\u0627 \u0634\u0646\u0627\u0633\u0647 \u0633\u0631\u0648\u06cc\u0633 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("smp_order_svc_"))
async def smp_order_svc(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        svc  = next((s for s in svcs if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("\u274c \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True); return
        await state.update_data(smp_svc_id=svc_id, smp_svc=svc)
        await state.set_state(SMPState.order_link)
        await cb.message.edit_text(
            f"\u2795 <b>\u0633\u0641\u0627\u0631\u0634 [{svc_id}] {svc['name']}</b>\n\n"
            f"\U0001f4b0 \u0646\u0631\u062e: ${svc['rate']} / 1000\n"
            f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: {svc['min']} | \U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: {svc['max']}\n"
            + ("\U0001f4c6 <i>\u0627\u06cc\u0646 \u0633\u0631\u0648\u06cc\u0633 Drip-feed \u062f\u0627\u0631\u062f</i>\n" if svc["dripfeed"] else "")
            + f"\n\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
            parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"\u274c {str(e)[:60]}", show_alert=True)


@router.message(SMPState.order_link)
async def smp_order_link(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    link = (msg.text or "").strip()
    if not link.startswith("http"):
        await msg.answer("\u274c \u0644\u06cc\u0646\u06a9 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    svc  = data.get("smp_svc", {})
    await state.update_data(smp_link=link)
    await state.set_state(SMPState.order_quantity)
    await msg.answer(
        f"\U0001f522 \u062a\u0639\u062f\u0627\u062f \u0645\u0648\u0631\u062f \u0646\u06cc\u0627\u0632:\n"
        f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: <b>{svc.get('min','?')}</b> | "
        f"\U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{svc.get('max','?')}</b>",
        parse_mode="HTML")


@router.message(SMPState.order_quantity)
async def smp_order_quantity(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return

    data   = await state.get_data()
    svc    = data.get("smp_svc", {})
    try:
        mn = int(float(svc.get("min", 1)))
        mx = int(float(svc.get("max", 999999)))
    except: mn, mx = 1, 999999

    if qty < mn or qty > mx:
        await msg.answer(
            f"\u274c \u062a\u0639\u062f\u0627\u062f \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 <b>{mn}</b> \u0648 <b>{mx}</b> \u0628\u0627\u0634\u062f.",
            parse_mode="HTML"); return

    await state.update_data(smp_qty=qty)

    # If dripfeed supported, ask for runs
    if svc.get("dripfeed"):
        await state.set_state(SMPState.order_runs)
        await msg.answer(
            "\U0001f4c6 <b>Drip-feed</b>\n\n"
            "\u062a\u0639\u062f\u0627\u062f \u0631\u0627\u0646 (runs) \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:\n"
            "<i>\u0628\u0631\u0627\u06cc \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u06a9\u0631\u062f\u0646 Drip-feed \u0639\u062f\u062f 0 \u0628\u0632\u0646\u06cc\u062f</i>",
            parse_mode="HTML")
    else:
        await state.set_state(None)
        await _submit_order(msg, state)


@router.message(SMPState.order_runs)
async def smp_order_runs(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: runs = int((msg.text or "").strip())
    except: await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.update_data(smp_runs=runs)
    if runs > 0:
        await state.set_state(SMPState.order_interval)
        await msg.answer(
            "\u23f1 \u0641\u0627\u0635\u0644\u0647 \u0632\u0645\u0627\u0646\u06cc \u0628\u06cc\u0646 \u0631\u0627\u0646\u200c\u0647\u0627 (\u062f\u0642\u06cc\u0642\u0647) \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
            parse_mode="HTML")
    else:
        await state.update_data(smp_interval=0)
        await state.set_state(None)
        await _submit_order(msg, state)


@router.message(SMPState.order_interval)
async def smp_order_interval(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: interval = int((msg.text or "").strip())
    except: await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.update_data(smp_interval=interval)
    await state.set_state(None)
    await _submit_order(msg, state)


async def _submit_order(msg: Message, state: FSMContext):
    data     = await state.get_data()
    svc_id   = data["smp_svc_id"]
    svc      = data["smp_svc"]
    link     = data["smp_link"]
    qty      = data["smp_qty"]
    runs     = data.get("smp_runs", 0)
    interval = data.get("smp_interval", 0)
    await state.clear()

    try: rate = float(svc.get("rate", 0))
    except: rate = 0.0
    cost = (rate * qty) / 1000

    df_info = f"\U0001f4c6 Drip-feed: {runs} \u0631\u0627\u0646 / {interval} \u062f\u0642\u06cc\u0642\u0647\n" if runs > 0 else ""

    status_msg = await msg.answer(
        f"\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634...\n"
        f"\U0001f539 [{svc_id}] {svc['name']}\n"
        f"\U0001f517 <code>{link[:50]}</code>\n"
        f"\U0001f522 \u062a\u0639\u062f\u0627\u062f: <b>{qty:,}</b>\n"
        f"{df_info}"
        f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647 \u062a\u062e\u0645\u06cc\u0646\u06cc: <b>${cost:.4f}</b>",
        parse_mode="HTML")
    try:
        from services.smmpass import add_order
        result   = await add_order(svc_id, link, qty, runs, interval)
        order_id = result["order"]
        await status_msg.edit_text(
            f"\u2705 <b>\u0633\u0641\u0627\u0631\u0634 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
            f"\U0001f4e6 \u0634\u0646\u0627\u0633\u0647: <code>{order_id}</code>\n"
            f"\U0001f539 {svc['name']}\n"
            f"\U0001f522 {qty:,} | \U0001f4b0 ${cost:.4f}\n"
            f"{df_info}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634 #{order_id}",
                    callback_data=f"smp_check_{order_id}"
                )],
                [InlineKeyboardButton(text="\U0001f519 \u0645\u0646\u0648", callback_data="smp_menu")],
            ]),
            parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(
            f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u062b\u0628\u062a:\n<code>{str(e)[:120]}</code>",
            reply_markup=smp_main_menu(), parse_mode="HTML")


# ─── Order Status ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_order_status")
async def smp_status_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SMPState.order_status)
    await cb.message.edit_text(
        "\U0001f4e6 <b>\u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634</b>\n\nID \u0633\u0641\u0627\u0631\u0634 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML")


@router.message(SMPState.order_status)
async def smp_status_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: oid = int((msg.text or "").strip())
    except: await msg.answer("\u274c ID \u0639\u062f\u062f\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.clear()
    await _show_status(msg, oid)


@router.callback_query(F.data.startswith("smp_check_"))
async def smp_check(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc...")
    oid = int(cb.data.split("_")[-1])
    await _show_status(cb.message, oid, edit=True)


async def _show_status(target, oid: int, edit: bool = False):
    try:
        from services.smmpass import get_order_status
        d    = await get_order_status(oid)
        icon = _icon(d["status"])
        text = (
            f"\U0001f4e6 <b>\u0633\u0641\u0627\u0631\u0634 #{oid}</b>\n\n"
            f"{icon} \u0648\u0636\u0639\u06cc\u062a: <b>{d['status']}</b>\n"
            f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>${d['charge']}</b>\n"
            f"\U0001f4ca \u0634\u0631\u0648\u0639: {d['start_count']} | \u0628\u0627\u0642\u06cc\u200c\u0645\u0627\u0646\u062f\u0647: {d['remains']}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f504 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc",
                                  callback_data=f"smp_check_{oid}")],
            [InlineKeyboardButton(text=f"\U0001f504 \u0631\u06cc\u0641\u06cc\u0644 \u0633\u0641\u0627\u0631\u0634 #{oid}",
                                  callback_data=f"smp_do_refill_{oid}")],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="smp_menu")],
        ])
        if edit: await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:    await target.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        err = f"\u274c <code>{str(e)[:120]}</code>"
        if edit: await target.edit_text(err, reply_markup=smp_main_menu(), parse_mode="HTML")
        else:    await target.answer(err, reply_markup=smp_main_menu(), parse_mode="HTML")


# ─── Batch Status ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_batch_status")
async def smp_batch_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SMPState.batch_status)
    await cb.message.edit_text(
        "\U0001f4ca <b>\u0648\u0636\u0639\u06cc\u062a \u0686\u0646\u062f \u0633\u0641\u0627\u0631\u0634</b>\n\n"
        "ID \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627 \u0631\u0627 \u0628\u0627 \u06a9\u0627\u0645\u0627 \u062c\u062f\u0627 \u06a9\u0646\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: 12,13,14</i>",
        parse_mode="HTML")


@router.message(SMPState.batch_status)
async def smp_batch_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    raw = (msg.text or "").strip()
    await state.clear()
    try:
        ids = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
        if not ids: raise ValueError("\u0634\u0646\u0627\u0633\u0647\u200c\u0647\u0627 \u0645\u0639\u062a\u0628\u0631 \u0646\u06cc\u0633\u062a\u0646\u062f")
        if len(ids) > 100: raise ValueError("\u062d\u062f\u0627\u06a9\u062b\u0631 100 \u0633\u0641\u0627\u0631\u0634")
    except ValueError as e:
        await msg.answer(f"\u274c {e}"); return

    status_msg = await msg.answer(f"\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0648\u0636\u0639\u06cc\u062a {len(ids)} \u0633\u0641\u0627\u0631\u0634...",
                                  parse_mode="HTML")
    try:
        from services.smmpass import get_orders_status
        results = await get_orders_status(ids)
        lines   = []
        for k, v in results.items():
            if isinstance(v, dict):
                icon = _icon(v["status"])
                lines.append(
                    f"{icon} <b>#{k}</b>: {v['status']} | ${v['charge']} | \u0628\u0627\u0642\u06cc: {v['remains']}"
                )
            else:
                lines.append(f"\u274c <b>#{k}</b>: {v}")
        text = "\U0001f4ca <b>\u0646\u062a\u0627\u06cc\u062c \u0628\u0627\u0686</b>\n\n" + "\n".join(lines)
        await status_msg.edit_text(text[:4000],
                                   reply_markup=smp_main_menu(), parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                                   reply_markup=smp_main_menu(), parse_mode="HTML")


# ─── Refill ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "smp_refill")
async def smp_refill_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SMPState.refill_order)
    await cb.message.edit_text(
        "\U0001f504 <b>\u0631\u06cc\u0641\u06cc\u0644 \u0633\u0641\u0627\u0631\u0634</b>\n\nID \u0633\u0641\u0627\u0631\u0634 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("smp_do_refill_"))
async def smp_do_refill_cb(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0631\u06cc\u0641\u06cc\u0644...")
    oid = int(cb.data.split("_")[-1])
    await _do_refill(cb.message, oid, edit=True)


@router.message(SMPState.refill_order)
async def smp_refill_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: oid = int((msg.text or "").strip())
    except: await msg.answer("\u274c ID \u0639\u062f\u062f\u06cc \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.clear()
    await _do_refill(msg, oid)


async def _do_refill(target, oid: int, edit: bool = False):
    try:
        from services.smmpass import create_refill
        result    = await create_refill(oid)
        refill_id = result["refill"]
        text = (
            f"\u2705 <b>\u0631\u06cc\u0641\u06cc\u0644 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
            f"\U0001f4e6 \u0633\u0641\u0627\u0631\u0634: <code>{oid}</code>\n"
            f"\U0001f504 \u0634\u0646\u0627\u0633\u0647 \u0631\u06cc\u0641\u06cc\u0644: <code>{refill_id}</code>"
        )
        if edit: await target.edit_text(text, reply_markup=smp_main_menu(), parse_mode="HTML")
        else:    await target.answer(text, reply_markup=smp_main_menu(), parse_mode="HTML")
    except Exception as e:
        err = f"\u274c <code>{str(e)[:120]}</code>"
        if edit: await target.edit_text(err, reply_markup=smp_main_menu(), parse_mode="HTML")
        else:    await target.answer(err, reply_markup=smp_main_menu(), parse_mode="HTML")
