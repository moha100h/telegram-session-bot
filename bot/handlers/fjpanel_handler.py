"""
FJPanel SMM Panel handler — fixed version.
All type-safe, no bool.lower() errors.
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

logger   = logging.getLogger("fjpanel")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PAGE_SIZE = 8


# ─── FSM ────────────────────────────────────────────────────────────────────
class FJState(StatesGroup):
    search_query   = State()
    order_link     = State()
    order_quantity = State()
    order_status   = State()


# ─── Helpers ────────────────────────────────────────────────────────────────
def _status_icon(status: str) -> str:
    s = status.lower()
    if any(x in s for x in ("complet", "done", "finish")):
        return "\u2705"
    if any(x in s for x in ("pending", "process", "progress", "active")):
        return "\u23f3"
    if any(x in s for x in ("cancel", "fail", "error", "refund")):
        return "\u274c"
    if "partial" in s:
        return "\u26a0\ufe0f"
    return "\U0001f7e1"


# ─── Keyboards ──────────────────────────────────────────────────────────────
def fj_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4b0 \u0645\u0648\u062c\u0648\u062f\u06cc \u062d\u0633\u0627\u0628",       callback_data="fj_balance")],
        [InlineKeyboardButton(text="\U0001f4cb \u0644\u06cc\u0633\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",      callback_data="fj_services_0")],
        [InlineKeyboardButton(text="\U0001f504 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627", callback_data="fj_refresh_services")],
        [InlineKeyboardButton(text="\U0001f50d \u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",  callback_data="fj_search")],
        [InlineKeyboardButton(text="\u2795 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u062c\u062f\u06cc\u062f",     callback_data="fj_new_order")],
        [InlineKeyboardButton(text="\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634",        callback_data="fj_order_status")],
        [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",              callback_data="menu_main")],
    ])


def _services_kb(services: list, page: int) -> InlineKeyboardMarkup:
    total = len(services)
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    chunk = services[start:end]

    rows = []
    for s in chunk:
        name  = s["name"][:30]
        rate  = s["rate"]
        label = f"\U0001f539 [{s['service']}] {name} | {rate} \u0631\u06cc\u0627\u0644"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"fj_svc_{s['service']}"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05\ufe0f \u0642\u0628\u0644",
                                        callback_data=f"fj_services_{page-1}"))
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}",
                                    callback_data="fj_noop"))
    if end < total:
        nav.append(InlineKeyboardButton(text="\u0628\u0639\u062f \u27a1\ufe0f",
                                        callback_data=f"fj_services_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",
                                      callback_data="fj_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Entry ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_fjpanel")
async def fj_entry(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f", show_alert=True)
        return
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "\U0001f6e0 <b>FJPanel \u2014 \u067e\u0646\u0644 SMM</b>\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=fj_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "fj_menu")
async def fj_menu_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "\U0001f6e0 <b>FJPanel \u2014 \u067e\u0646\u0644 SMM</b>\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=fj_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "fj_noop")
async def fj_noop(cb: CallbackQuery):
    await cb.answer()


# ─── Balance ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_balance")
async def fj_balance(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    msg = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0645\u0648\u062c\u0648\u062f\u06cc...",
                                     parse_mode="HTML")
    try:
        from services.fjpanel import get_balance
        data     = await get_balance()
        balance  = data["balance"]
        currency = data["currency"]
        try:
            bal_fmt = f"{float(balance):,.2f}"
        except ValueError:
            bal_fmt = balance
        text = (
            f"\U0001f4b0 <b>\u0645\u0648\u062c\u0648\u062f\u06cc \u062d\u0633\u0627\u0628 FJPanel</b>\n\n"
            f"\U0001f4b5 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>{bal_fmt}</b> {currency}"
        )
    except Exception as e:
        text = f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>"
    await msg.edit_text(text, reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Services list ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_refresh_services")
async def fj_refresh_services(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc...")
    msg = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 \u0627\u0632 \u0633\u0627\u06cc\u062a...",
                                     parse_mode="HTML")
    try:
        from services.fjpanel import get_services
        services = await get_services(force=True)
        await msg.edit_text(
            f"\u2705 <b>{len(services)}</b> \u0633\u0631\u0648\u06cc\u0633 \u0628\u0647\u200c\u0631\u0648\u0632 \u0634\u062f.",
            reply_markup=fj_main_menu(), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(
            f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
            reply_markup=fj_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_services_"))
async def fj_services(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    page = int(cb.data.split("_")[-1])

    # Check if category filter active
    data       = await state.get_data()
    cat_filter = data.get("fj_cat", "")

    msg = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627...",
                                     parse_mode="HTML")
    try:
        from services.fjpanel import get_services
        all_svcs = await get_services()
        if not all_svcs:
            await msg.edit_text("\u274c \u0633\u0631\u0648\u06cc\u0633\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f. \u0627\u0628\u062a\u062f\u0627 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u06a9\u0646\u06cc\u062f.",
                                reply_markup=fj_main_menu(), parse_mode="HTML")
            return

        # Filter
        services = [s for s in all_svcs
                    if not cat_filter or s["category"] == cat_filter]

        # Category buttons (top)
        cats = list(dict.fromkeys(s["category"] for s in all_svcs))
        cat_rows = []
        for i in range(0, len(cats), 2):
            row = []
            for cat in cats[i:i+2]:
                active = "\u2705 " if cat == cat_filter else ""
                row.append(InlineKeyboardButton(
                    text=f"{active}{cat[:22]}",
                    callback_data=f"fj_cat_{cat[:30]}"
                ))
            cat_rows.append(row)
        if cat_filter:
            cat_rows.append([InlineKeyboardButton(
                text="\u274c \u062d\u0630\u0641 \u0641\u06cc\u0644\u062a\u0631",
                callback_data="fj_cat_CLEAR"
            )])

        svc_kb   = _services_kb(services, page)
        all_rows = cat_rows + svc_kb.inline_keyboard
        kb       = InlineKeyboardMarkup(inline_keyboard=all_rows)

        header = f"\U0001f4cc \u062f\u0633\u062a\u0647: <b>{cat_filter}</b>\n" if cat_filter else ""
        await msg.edit_text(
            f"\U0001f4ca <b>\u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 ({len(services)} \u0645\u0648\u0631\u062f)</b>\n{header}"
            f"\u0631\u0648\u06cc \u0647\u0631 \u0633\u0631\u0648\u06cc\u0633 \u0628\u0632\u0646\u06cc\u062f \u062a\u0627 \u062c\u0632\u0626\u06cc\u0627\u062a \u0628\u0628\u06cc\u0646\u06cc\u062f:",
            reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(
            f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
            reply_markup=fj_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_cat_"))
async def fj_cat_filter(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cat = cb.data[7:]
    if cat == "CLEAR":
        await state.update_data(fj_cat="")
    else:
        await state.update_data(fj_cat=cat)
    cb.data = "fj_services_0"
    await fj_services(cb, state)


@router.callback_query(F.data.startswith("fj_svc_"))
async def fj_service_detail(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.fjpanel import get_services
        services = await get_services()
        svc = next((s for s in services if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("\u274c \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True)
            return
        text = (
            f"\U0001f539 <b>{svc['name']}</b>\n\n"
            f"\U0001f3f7 \u062f\u0633\u062a\u0647: <code>{svc['category']}</code>\n"
            f"\U0001f522 \u0634\u0646\u0627\u0633\u0647: <code>{svc['service']}</code>\n"
            f"\U0001f4b0 \u0646\u0631\u062e: <b>{svc['rate']}</b> \u0631\u06cc\u0627\u0644 / 1000\n"
            f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: <b>{svc['min']}</b>\n"
            f"\U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{svc['max']}</b>\n"
            f"\U0001f4cc \u0646\u0648\u0639: <code>{svc['type']}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"\u2795 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u0628\u0627 \u0633\u0631\u0648\u06cc\u0633 {svc_id}",
                callback_data=f"fj_order_svc_{svc_id}"
            )],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",
                                  callback_data="fj_services_0")],
        ])
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"\u274c {str(e)[:60]}", show_alert=True)


# ─── Search ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_search")
async def fj_search_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(FJState.search_query)
    await cb.message.edit_text(
        "\U0001f50d <b>\u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627</b>\n\n"
        "\u0646\u0627\u0645 \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627 \u062f\u0633\u062a\u0647 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: followers, instagram, like</i>",
        parse_mode="HTML")


@router.message(FJState.search_query)
async def fj_search_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    query = (msg.text or "").strip().lower()
    await state.clear()
    try:
        from services.fjpanel import get_services
        services = await get_services()
        results  = [
            s for s in services
            if query in s["name"].lower()
            or query in s["category"].lower()
            or query == str(s["service"])
        ]
        if not results:
            await msg.answer(
                f"\u274c \u0646\u062a\u06cc\u062c\u0647\u200c\u0627\u06cc \u0628\u0631\u0627\u06cc '<b>{query}</b>' \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.",
                reply_markup=fj_main_menu(), parse_mode="HTML")
            return
        rows = []
        for s in results[:20]:
            rows.append([InlineKeyboardButton(
                text=f"\U0001f539 [{s['service']}] {s['name'][:28]} | {s['rate']} \u0631\u06cc\u0627\u0644",
                callback_data=f"fj_svc_{s['service']}"
            )])
        rows.append([InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",
                                          callback_data="fj_menu")])
        suffix = f" (\u0627\u0648\u0644 20 \u0646\u0645\u0627\u06cc\u0634 \u062f\u0627\u062f\u0647 \u0634\u062f)" if len(results) > 20 else ""
        await msg.answer(
            f"\U0001f50d \u0646\u062a\u0627\u06cc\u062c '<b>{query}</b>': <b>{len(results)}</b> \u0645\u0648\u0631\u062f{suffix}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
                         reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── New Order ───────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_new_order")
async def fj_new_order(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(FJState.search_query)
    await state.update_data(fj_order_mode=True)
    await cb.message.edit_text(
        "\u2795 <b>\u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u062c\u062f\u06cc\u062f</b>\n\n"
        "\u0646\u0627\u0645 \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627 \u0634\u0646\u0627\u0633\u0647 \u0633\u0631\u0648\u06cc\u0633 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: followers \u06cc\u0627 110</i>",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_order_svc_"))
async def fj_order_svc(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.fjpanel import get_services
        services = await get_services()
        svc = next((s for s in services if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("\u274c \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True)
            return
        await state.update_data(fj_svc_id=svc_id, fj_svc=svc)
        await state.set_state(FJState.order_link)
        await cb.message.edit_text(
            f"\u2795 <b>\u0633\u0641\u0627\u0631\u0634 [{svc_id}] {svc['name']}</b>\n\n"
            f"\U0001f4b0 \u0646\u0631\u062e: {svc['rate']} \u0631\u06cc\u0627\u0644 / 1000\n"
            f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: {svc['min']} | \U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: {svc['max']}\n\n"
            f"\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
            parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"\u274c {str(e)[:60]}", show_alert=True)


@router.message(FJState.order_link)
async def fj_order_link(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    link = (msg.text or "").strip()
    if not link.startswith("http"):
        await msg.answer("\u274c \u0644\u06cc\u0646\u06a9 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    svc  = data.get("fj_svc", {})
    await state.update_data(fj_link=link)
    await state.set_state(FJState.order_quantity)
    await msg.answer(
        f"\U0001f522 \u062a\u0639\u062f\u0627\u062f \u0645\u0648\u0631\u062f \u0646\u06cc\u0627\u0632 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:\n"
        f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: <b>{svc.get('min','?')}</b> | "
        f"\U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{svc.get('max','?')}</b>",
        parse_mode="HTML")


@router.message(FJState.order_quantity)
async def fj_order_quantity(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return

    data   = await state.get_data()
    svc_id = data["fj_svc_id"]
    svc    = data["fj_svc"]
    link   = data["fj_link"]
    await state.clear()

    try:
        mn = int(float(svc.get("min", 1)))
        mx = int(float(svc.get("max", 999999)))
    except (ValueError, TypeError):
        mn, mx = 1, 999999

    if qty < mn or qty > mx:
        await msg.answer(
            f"\u274c \u062a\u0639\u062f\u0627\u062f \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 <b>{mn}</b> \u0648 <b>{mx}</b> \u0628\u0627\u0634\u062f.",
            parse_mode="HTML"); return

    try:
        rate = float(svc.get("rate", 0))
    except (ValueError, TypeError):
        rate = 0.0
    cost = (rate * qty) / 1000

    status_msg = await msg.answer(
        f"\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634...\n"
        f"\U0001f539 \u0633\u0631\u0648\u06cc\u0633: [{svc_id}] {svc['name']}\n"
        f"\U0001f517 \u0644\u06cc\u0646\u06a9: <code>{link[:50]}</code>\n"
        f"\U0001f522 \u062a\u0639\u062f\u0627\u062f: <b>{qty:,}</b>\n"
        f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647 \u062a\u062e\u0645\u06cc\u0646\u06cc: <b>{cost:,.2f}</b> \u0631\u06cc\u0627\u0644",
        parse_mode="HTML")
    try:
        from services.fjpanel import add_order
        result   = await add_order(svc_id, link, qty)
        order_id = result["order"]
        await status_msg.edit_text(
            f"\u2705 <b>\u0633\u0641\u0627\u0631\u0634 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
            f"\U0001f4e6 \u0634\u0646\u0627\u0633\u0647 \u0633\u0641\u0627\u0631\u0634: <code>{order_id}</code>\n"
            f"\U0001f539 \u0633\u0631\u0648\u06cc\u0633: {svc['name']}\n"
            f"\U0001f522 \u062a\u0639\u062f\u0627\u062f: {qty:,}\n"
            f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647 \u062a\u062e\u0645\u06cc\u0646\u06cc: {cost:,.2f} \u0631\u06cc\u0627\u0644",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634 #{order_id}",
                    callback_data=f"fj_check_{order_id}"
                )],
                [InlineKeyboardButton(text="\U0001f519 \u0645\u0646\u0648",
                                      callback_data="fj_menu")],
            ]),
            parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(
            f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634:\n<code>{str(e)[:120]}</code>",
            reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Order Status ────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_order_status")
async def fj_order_status_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(FJState.order_status)
    await cb.message.edit_text(
        "\U0001f4e6 <b>\u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634</b>\n\n"
        "\u0634\u0646\u0627\u0633\u0647 \u0633\u0641\u0627\u0631\u0634 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML")


@router.message(FJState.order_status)
async def fj_order_status_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        order_id = int((msg.text or "").strip())
    except ValueError:
        await msg.answer("\u274c \u0634\u0646\u0627\u0633\u0647 \u0633\u0641\u0627\u0631\u0634 \u0628\u0627\u06cc\u062f \u0639\u062f\u062f \u0628\u0627\u0634\u062f."); return
    await state.clear()
    await _show_order_status(msg, order_id)


@router.callback_query(F.data.startswith("fj_check_"))
async def fj_check_order(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc...")
    order_id = int(cb.data.split("_")[-1])
    await _show_order_status(cb.message, order_id, edit=True)


async def _show_order_status(target, order_id: int, edit: bool = False):
    try:
        from services.fjpanel import get_order_status
        data     = await get_order_status(order_id)
        status   = data["status"]
        charge   = data["charge"]
        currency = data["currency"]
        icon     = _status_icon(status)
        text = (
            f"\U0001f4e6 <b>\u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634 #{order_id}</b>\n\n"
            f"{icon} \u0648\u0636\u0639\u06cc\u062a: <b>{status}</b>\n"
            f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>{charge}</b> {currency}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f504 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc",
                                  callback_data=f"fj_check_{order_id}")],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",
                                  callback_data="fj_menu")],
        ])
        if edit:
            await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        err = f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>"
        if edit:
            await target.edit_text(err, reply_markup=fj_main_menu(), parse_mode="HTML")
        else:
            await target.answer(err, reply_markup=fj_main_menu(), parse_mode="HTML")
