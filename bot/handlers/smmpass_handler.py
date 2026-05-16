"""
SMMPass SMM Panel handler.
Features: balance, services list (paginated + category filter + search),
          all order types, order status (single + multi), refresh.
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
class SPState(StatesGroup):
    search        = State()
    order_link    = State()
    order_qty     = State()
    order_extra   = State()   # for comments/usernames/hashtags
    order_status  = State()
    multi_status  = State()
    sub_username  = State()
    sub_min       = State()
    sub_max       = State()


# ─── Helpers ────────────────────────────────────────────────────────────────
def _status_icon(status: str) -> str:
    s = status.lower()
    if any(x in s for x in ("complet", "done", "finish")): return "\u2705"
    if any(x in s for x in ("pending", "process", "progress", "active")): return "\u23f3"
    if any(x in s for x in ("cancel", "fail", "error", "refund")): return "\u274c"
    if "partial" in s: return "\u26a0\ufe0f"
    return "\U0001f7e1"


def _type_label(t: str) -> str:
    labels = {
        "default":                  "\U0001f4e6 Default",
        "package":                  "\U0001f381 Package",
        "custom comments":          "\U0001f4ac Custom Comments",
        "mentions with hashtags":   "\U0001f3f7 Mentions+Hashtags",
        "mentions custom list":     "\U0001f4cb Mentions Custom",
        "mentions hashtag":         "#\ufe0f\u20e3 Mentions Hashtag",
        "mentions user followers":  "\U0001f465 Mentions Followers",
        "mentions media likers":    "\u2764\ufe0f Mentions Likers",
        "custom comments package":  "\U0001f4ac\U0001f381 Comments Pkg",
        "comment likes":            "\U0001f44d Comment Likes",
        "subscriptions":            "\U0001f504 Subscription",
    }
    return labels.get(t.lower(), f"\U0001f539 {t.title()}")


# ─── Keyboards ──────────────────────────────────────────────────────────────
def sp_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f4b0 \u0645\u0648\u062c\u0648\u062f\u06cc \u062d\u0633\u0627\u0628",        callback_data="sp_balance")],
        [InlineKeyboardButton(text="\U0001f4cb \u0644\u06cc\u0633\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",       callback_data="sp_services_0")],
        [InlineKeyboardButton(text="\U0001f504 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",  callback_data="sp_refresh_svcs")],
        [InlineKeyboardButton(text="\U0001f50d \u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627",   callback_data="sp_search")],
        [InlineKeyboardButton(text="\u2795 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u062c\u062f\u06cc\u062f",      callback_data="sp_new_order")],
        [InlineKeyboardButton(text="\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634",         callback_data="sp_order_status")],
        [InlineKeyboardButton(text="\U0001f4e6\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0686\u0646\u062f \u0633\u0641\u0627\u0631\u0634",  callback_data="sp_multi_status")],
        [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",               callback_data="menu_main")],
    ])


def _svcs_kb(services: list, page: int) -> InlineKeyboardMarkup:
    total = len(services)
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    rows  = []
    for s in services[start:end]:
        rows.append([InlineKeyboardButton(
            text=f"\U0001f539 [{s['service']}] {s['name'][:26]} | ${s['rate']}",
            callback_data=f"sp_svc_{s['service']}"
        )])
    nav = []
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05\ufe0f", callback_data=f"sp_services_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="sp_noop"))
    if end < total:
        nav.append(InlineKeyboardButton(text="\u27a1\ufe0f", callback_data=f"sp_services_{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="sp_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Entry ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_smmpass")
async def sp_entry(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "\U0001f680 <b>SMMPass \u2014 \u067e\u0646\u0644 SMM</b>\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=sp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "sp_menu")
async def sp_menu_back(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "\U0001f680 <b>SMMPass \u2014 \u067e\u0646\u0644 SMM</b>\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=sp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data == "sp_noop")
async def sp_noop(cb: CallbackQuery):
    await cb.answer()


# ─── Balance ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_balance")
async def sp_balance(cb: CallbackQuery):
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
            f"\U0001f4b5 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>{bal}</b> {d['currency']}",
            reply_markup=sp_main_menu(), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                            reply_markup=sp_main_menu(), parse_mode="HTML")


# ─── Services ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_refresh_svcs")
async def sp_refresh_svcs(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc...")
    msg = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 \u0627\u0632 \u0633\u0627\u06cc\u062a...", parse_mode="HTML")
    try:
        from services.smmpass import get_services
        svcs = await get_services(force=True)
        await msg.edit_text(
            f"\u2705 <b>{len(svcs)}</b> \u0633\u0631\u0648\u06cc\u0633 \u0628\u0647\u200c\u0631\u0648\u0632 \u0634\u062f.",
            reply_markup=sp_main_menu(), parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                            reply_markup=sp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("sp_services_"))
async def sp_services(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    data = await state.get_data()
    cat  = data.get("sp_cat", "")
    msg  = await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062f\u0631\u06cc\u0627\u0641\u062a...", parse_mode="HTML")
    try:
        from services.smmpass import get_services
        all_svcs = await get_services()
        if not all_svcs:
            await msg.edit_text("\u274c \u0633\u0631\u0648\u06cc\u0633\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f. \u0627\u0628\u062a\u062f\u0627 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u06a9\u0646\u06cc\u062f.",
                                reply_markup=sp_main_menu(), parse_mode="HTML"); return
        svcs = [s for s in all_svcs if not cat or s["category"] == cat]
        cats = list(dict.fromkeys(s["category"] for s in all_svcs))
        cat_rows = []
        for i in range(0, len(cats), 2):
            row = []
            for c in cats[i:i+2]:
                active = "\u2705 " if c == cat else ""
                row.append(InlineKeyboardButton(
                    text=f"{active}{c[:22]}",
                    callback_data=f"sp_cat_{c[:30]}"
                ))
            cat_rows.append(row)
        if cat:
            cat_rows.append([InlineKeyboardButton(
                text="\u274c \u062d\u0630\u0641 \u0641\u06cc\u0644\u062a\u0631", callback_data="sp_cat_CLEAR")])
        svc_kb   = _svcs_kb(svcs, page)
        all_rows = cat_rows + svc_kb.inline_keyboard
        header   = f"\U0001f4cc \u062f\u0633\u062a\u0647: <b>{cat}</b>\n" if cat else ""
        await msg.edit_text(
            f"\U0001f4ca <b>\u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 ({len(svcs)} \u0645\u0648\u0631\u062f)</b>\n{header}"
            "\u0631\u0648\u06cc \u0647\u0631 \u0633\u0631\u0648\u06cc\u0633 \u0628\u0632\u0646\u06cc\u062f:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=all_rows),
            parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"\u274c <code>{str(e)[:120]}</code>",
                            reply_markup=sp_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("sp_cat_"))
async def sp_cat(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cat = cb.data[7:]
    await state.update_data(sp_cat="" if cat == "CLEAR" else cat)
    cb.data = "sp_services_0"
    await sp_services(cb, state)


@router.callback_query(F.data.startswith("sp_svc_"))
async def sp_svc_detail(cb: CallbackQuery, state: FSMContext):
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
        drip = "\u2705" if svc["dripfeed"] else "\u274c"
        text = (
            f"\U0001f539 <b>{svc['name']}</b>\n\n"
            f"\U0001f3f7 \u062f\u0633\u062a\u0647: <code>{svc['category']}</code>\n"
            f"\U0001f522 \u0634\u0646\u0627\u0633\u0647: <code>{svc['service']}</code>\n"
            f"\U0001f4b0 \u0646\u0631\u062e: <b>${svc['rate']}</b> / 1000\n"
            f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: <b>{svc['min']}</b>\n"
            f"\U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{svc['max']}</b>\n"
            f"\U0001f4cc \u0646\u0648\u0639: <code>{_type_label(svc['type'])}</code>\n"
            f"\U0001f504 Drip Feed: {drip}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"\u2795 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 [{svc_id}]",
                callback_data=f"sp_order_{svc_id}"
            )],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="sp_services_0")],
        ])
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"\u274c {str(e)[:60]}", show_alert=True)


# ─── Search ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_search")
async def sp_search_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SPState.search)
    await cb.message.edit_text(
        "\U0001f50d <b>\u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627</b>\n\n"
        "\u0646\u0627\u0645 \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627 \u062f\u0633\u062a\u0647 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: telegram, views, members</i>",
        parse_mode="HTML")


@router.message(SPState.search)
async def sp_search_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    q = (msg.text or "").strip().lower()
    await state.clear()
    try:
        from services.smmpass import get_services
        svcs    = await get_services()
        results = [s for s in svcs
                   if q in s["name"].lower() or q in s["category"].lower()
                   or q == str(s["service"])]
        if not results:
            await msg.answer(f"\u274c \u0646\u062a\u06cc\u062c\u0647\u200c\u0627\u06cc \u0628\u0631\u0627\u06cc '<b>{q}</b>' \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.",
                             reply_markup=sp_main_menu(), parse_mode="HTML"); return
        rows = [[InlineKeyboardButton(
            text=f"\U0001f539 [{s['service']}] {s['name'][:26]} | ${s['rate']}",
            callback_data=f"sp_svc_{s['service']}"
        )] for s in results[:20]]
        rows.append([InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="sp_menu")])
        suffix = " (\u0627\u0648\u0644 20)" if len(results) > 20 else ""
        await msg.answer(
            f"\U0001f50d '<b>{q}</b>': <b>{len(results)}</b> \u0645\u0648\u0631\u062f{suffix}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"\u274c <code>{str(e)[:120]}</code>",
                         reply_markup=sp_main_menu(), parse_mode="HTML")


# ─── Order flow ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_new_order")
async def sp_new_order(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SPState.search)
    await state.update_data(sp_order_mode=True)
    await cb.message.edit_text(
        "\u2795 <b>\u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634 \u062c\u062f\u06cc\u062f</b>\n\n"
        "\u0634\u0646\u0627\u0633\u0647 \u0633\u0631\u0648\u06cc\u0633 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: 5 \u06cc\u0627 telegram views</i>",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("sp_order_"))
async def sp_order_start(cb: CallbackQuery, state: FSMContext):
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
        await state.update_data(sp_svc=svc, sp_svc_id=svc_id)
        t = svc["type"]

        if t == "subscriptions":
            await state.set_state(SPState.sub_username)
            await cb.message.edit_text(
                f"\U0001f504 <b>Subscription [{svc_id}] {svc['name']}</b>\n\n"
                f"\U0001f4b0 \u0646\u0631\u062e: ${svc['rate']} / 1000\n"
                f"\U0001f4c9 Min: {svc['min']} | \U0001f4c8 Max: {svc['max']}\n\n"
                "\U0001f464 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
                parse_mode="HTML")
        elif t == "package":
            await state.set_state(SPState.order_link)
            await cb.message.edit_text(
                f"\U0001f381 <b>Package [{svc_id}] {svc['name']}</b>\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        elif t in ("custom comments", "custom comments package"):
            await state.set_state(SPState.order_link)
            await state.update_data(sp_next="comments")
            await cb.message.edit_text(
                f"\U0001f4ac <b>Custom Comments [{svc_id}]</b>\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        elif t == "mentions custom list":
            await state.set_state(SPState.order_link)
            await state.update_data(sp_next="usernames")
            await cb.message.edit_text(
                f"\U0001f4cb <b>Mentions Custom [{svc_id}]</b>\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        elif t in ("mentions with hashtags",):
            await state.set_state(SPState.order_link)
            await state.update_data(sp_next="mentions_hashtags")
            await cb.message.edit_text(
                f"\U0001f3f7 <b>Mentions+Hashtags [{svc_id}]</b>\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        elif t == "mentions hashtag":
            await state.set_state(SPState.order_link)
            await state.update_data(sp_next="hashtag")
            await cb.message.edit_text(
                f"#\ufe0f\u20e3 <b>Mentions Hashtag [{svc_id}]</b>\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        elif t in ("mentions user followers", "comment likes"):
            await state.set_state(SPState.order_link)
            await state.update_data(sp_next="username_qty")
            await cb.message.edit_text(
                f"\U0001f465 <b>{_type_label(t)} [{svc_id}]</b>\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        else:  # default
            await state.set_state(SPState.order_link)
            await state.update_data(sp_next="default")
            await cb.message.edit_text(
                f"\U0001f4e6 <b>Default [{svc_id}] {svc['name']}</b>\n\n"
                f"\U0001f4b0 \u0646\u0631\u062e: ${svc['rate']} / 1000\n"
                f"\U0001f4c9 \u062d\u062f\u0627\u0642\u0644: {svc['min']} | \U0001f4c8 \u062d\u062f\u0627\u06a9\u062b\u0631: {svc['max']}\n\n"
                "\U0001f517 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"\u274c {str(e)[:60]}", show_alert=True)


@router.message(SPState.order_link)
async def sp_order_link(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    link = (msg.text or "").strip()
    if not link.startswith("http"):
        await msg.answer("\u274c \u0644\u06cc\u0646\u06a9 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    await state.update_data(sp_link=link)
    nxt  = data.get("sp_next", "default")
    svc  = data.get("sp_svc", {})

    if nxt == "comments":
        await state.set_state(SPState.order_extra)
        await state.update_data(sp_extra_type="comments")
        await msg.answer("\U0001f4ac \u06a9\u0627\u0645\u0646\u062a\u200c\u0647\u0627 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f (\u0647\u0631 \u062e\u0637 \u06cc\u06a9 \u06a9\u0627\u0645\u0646\u062a):")
    elif nxt == "usernames":
        await state.set_state(SPState.order_extra)
        await state.update_data(sp_extra_type="usernames")
        await msg.answer("\U0001f464 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645\u200c\u0647\u0627 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f (\u0647\u0631 \u062e\u0637 \u06cc\u06a9 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645):")
    elif nxt == "mentions_hashtags":
        await state.set_state(SPState.order_qty)
        await state.update_data(sp_extra_type="mentions_hashtags")
        await msg.answer(f"\U0001f522 \u062a\u0639\u062f\u0627\u062f (\u062d\u062f\u0627\u0642\u0644 {svc.get('min','?')} | \u062d\u062f\u0627\u06a9\u062b\u0631 {svc.get('max','?')}):")
    elif nxt == "hashtag":
        await state.set_state(SPState.order_qty)
        await state.update_data(sp_extra_type="hashtag")
        await msg.answer(f"\U0001f522 \u062a\u0639\u062f\u0627\u062f (\u062d\u062f\u0627\u0642\u0644 {svc.get('min','?')} | \u062d\u062f\u0627\u06a9\u062b\u0631 {svc.get('max','?')}):")
    elif nxt == "username_qty":
        await state.set_state(SPState.order_qty)
        await state.update_data(sp_extra_type="username_qty")
        await msg.answer(f"\U0001f522 \u062a\u0639\u062f\u0627\u062f (\u062d\u062f\u0627\u0642\u0644 {svc.get('min','?')} | \u062d\u062f\u0627\u06a9\u062b\u0631 {svc.get('max','?')}):")
    elif svc.get("type") == "package":
        await state.clear()
        await _place_order_package(msg, data["sp_svc_id"], link)
    else:
        await state.set_state(SPState.order_qty)
        await msg.answer(f"\U0001f522 \u062a\u0639\u062f\u0627\u062f (\u062d\u062f\u0627\u0642\u0644 {svc.get('min','?')} | \u062d\u062f\u0627\u06a9\u062b\u0631 {svc.get('max','?')}):")


@router.message(SPState.order_qty)
async def sp_order_qty(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    svc  = data.get("sp_svc", {})
    et   = data.get("sp_extra_type", "default")
    await state.update_data(sp_qty=qty)

    if et == "mentions_hashtags":
        await state.set_state(SPState.order_extra)
        await state.update_data(sp_extra_type="mentions_hashtags_2")
        await msg.answer("\U0001f464 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645\u200c\u0647\u0627 (\u0647\u0631 \u062e\u0637 \u06cc\u06a9):")
    elif et == "hashtag":
        await state.set_state(SPState.order_extra)
        await state.update_data(sp_extra_type="hashtag_2")
        await msg.answer("#\ufe0f\u20e3 \u0647\u0634\u062a\u06af \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f (\u0628\u062f\u0648\u0646 #):")
    elif et == "username_qty":
        await state.set_state(SPState.order_extra)
        await state.update_data(sp_extra_type="username_qty_2")
        await msg.answer("\U0001f464 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:")
    else:
        await state.clear()
        await _place_order_default(msg, data["sp_svc_id"], data["sp_link"], qty, svc)


@router.message(SPState.order_extra)
async def sp_order_extra(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    extra = (msg.text or "").strip()
    data  = await state.get_data()
    et    = data.get("sp_extra_type", "")
    svc_id = data["sp_svc_id"]
    link   = data.get("sp_link", "")
    qty    = data.get("sp_qty", 0)
    await state.clear()

    try:
        from services import smmpass as sp
        if et == "comments":
            result = await sp.add_order_custom_comments(svc_id, link, extra)
        elif et == "usernames":
            result = await sp.add_order_mentions_custom(svc_id, link, extra)
        elif et == "mentions_hashtags_2":
            # extra = usernames, need hashtags next — simplified: split by |
            parts = extra.split("|")
            usernames = parts[0].strip()
            hashtags  = parts[1].strip() if len(parts) > 1 else ""
            result = await sp.add_order_mentions_hashtags(svc_id, link, qty, usernames, hashtags)
        elif et == "hashtag_2":
            result = await sp.add_order_mentions_hashtag(svc_id, link, qty, extra)
        elif et == "username_qty_2":
            result = await sp.add_order_mentions_followers(svc_id, link, qty, extra)
        else:
            await msg.answer("\u274c \u0646\u0648\u0639 \u0633\u0641\u0627\u0631\u0634 \u0646\u0627\u0645\u0634\u062e\u0635 \u0627\u0633\u062a.",
                             reply_markup=sp_main_menu(), parse_mode="HTML"); return
        await _order_success(msg, result["order"])
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
                         reply_markup=sp_main_menu(), parse_mode="HTML")


async def _place_order_default(msg, svc_id, link, qty, svc):
    try:
        from services.smmpass import add_order_default
        try: mn, mx = int(float(svc.get("min",1))), int(float(svc.get("max",999999)))
        except: mn, mx = 1, 999999
        if qty < mn or qty > mx:
            await msg.answer(f"\u274c \u062a\u0639\u062f\u0627\u062f \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 <b>{mn}</b> \u0648 <b>{mx}</b> \u0628\u0627\u0634\u062f.",
                             parse_mode="HTML"); return
        result = await add_order_default(svc_id, link, qty)
        await _order_success(msg, result["order"])
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
                         reply_markup=sp_main_menu(), parse_mode="HTML")


async def _place_order_package(msg, svc_id, link):
    try:
        from services.smmpass import add_order_package
        result = await add_order_package(svc_id, link)
        await _order_success(msg, result["order"])
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
                         reply_markup=sp_main_menu(), parse_mode="HTML")


async def _order_success(msg, order_id: int):
    await msg.answer(
        f"\u2705 <b>\u0633\u0641\u0627\u0631\u0634 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
        f"\U0001f4e6 \u0634\u0646\u0627\u0633\u0647: <code>{order_id}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"\U0001f4e6 \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634 #{order_id}",
                callback_data=f"sp_check_{order_id}"
            )],
            [InlineKeyboardButton(text="\U0001f519 \u0645\u0646\u0648", callback_data="sp_menu")],
        ]),
        parse_mode="HTML")


# ─── Subscription flow ──────────────────────────────────────────────────────────
@router.message(SPState.sub_username)
async def sp_sub_username(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    await state.update_data(sp_sub_user=msg.text.strip())
    await state.set_state(SPState.sub_min)
    data = await state.get_data()
    svc  = data.get("sp_svc", {})
    await msg.answer(f"\U0001f4c9 Min quantity (\u062d\u062f\u0627\u0642\u0644 {svc.get('min','?')}):")


@router.message(SPState.sub_min)
async def sp_sub_min(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: mn = int(msg.text.strip())
    except: await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.update_data(sp_sub_min=mn)
    await state.set_state(SPState.sub_max)
    data = await state.get_data()
    svc  = data.get("sp_svc", {})
    await msg.answer(f"\U0001f4c8 Max quantity (\u062d\u062f\u0627\u06a9\u062b\u0631 {svc.get('max','?')}):")


@router.message(SPState.sub_max)
async def sp_sub_max(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: mx = int(msg.text.strip())
    except: await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    await state.clear()
    try:
        from services.smmpass import add_order_subscription
        result = await add_order_subscription(
            data["sp_svc_id"], data["sp_sub_user"],
            data["sp_sub_min"], mx
        )
        await _order_success(msg, result["order"])
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627: <code>{str(e)[:120]}</code>",
                         reply_markup=sp_main_menu(), parse_mode="HTML")


# ─── Order Status ────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_order_status")
async def sp_status_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SPState.order_status)
    await cb.message.edit_text(
        "\U0001f4e6 <b>\u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634</b>\n\n"
        "\u0634\u0646\u0627\u0633\u0647 \u0633\u0641\u0627\u0631\u0634 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML")


@router.message(SPState.order_status)
async def sp_status_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try: oid = int((msg.text or "").strip())
    except: await msg.answer("\u274c \u0634\u0646\u0627\u0633\u0647 \u0628\u0627\u06cc\u062f \u0639\u062f\u062f \u0628\u0627\u0634\u062f."); return
    await state.clear()
    await _show_status(msg, oid)


@router.callback_query(F.data.startswith("sp_check_"))
async def sp_check(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\U0001f504 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0631\u0633\u06cc...")
    oid = int(cb.data.split("_")[-1])
    await _show_status(cb.message, oid, edit=True)


async def _show_status(target, oid: int, edit: bool = False):
    try:
        from services.smmpass import get_order_status
        d    = await get_order_status(oid)
        icon = _status_icon(d["status"])
        text = (
            f"\U0001f4e6 <b>\u0633\u0641\u0627\u0631\u0634 #{oid}</b>\n\n"
            f"{icon} \u0648\u0636\u0639\u06cc\u062a: <b>{d['status']}</b>\n"
            f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>${d['charge']}</b>\n"
            f"\U0001f4ca \u0634\u0631\u0648\u0639: <b>{d['start_count']}</b>\n"
            f"\u23f3 \u0628\u0627\u0642\u06cc\u0645\u0627\u0646\u062f\u0647: <b>{d['remains']}</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f504 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc",
                                  callback_data=f"sp_check_{oid}")],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="sp_menu")],
        ])
        if edit: await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:    await target.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        err = f"\u274c <code>{str(e)[:120]}</code>"
        if edit: await target.edit_text(err, reply_markup=sp_main_menu(), parse_mode="HTML")
        else:    await target.answer(err, reply_markup=sp_main_menu(), parse_mode="HTML")


# ─── Multi status ─────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_multi_status")
async def sp_multi_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(SPState.multi_status)
    await cb.message.edit_text(
        "\U0001f4e6\U0001f4e6 <b>\u0648\u0636\u0639\u06cc\u062a \u0686\u0646\u062f \u0633\u0641\u0627\u0631\u0634</b>\n\n"
        "\u0634\u0646\u0627\u0633\u0647\u200c\u0647\u0627 \u0631\u0627 \u0628\u0627 \u0648\u06cc\u0631\u06af\u0648\u0644 \u062c\u062f\u0627 \u06a9\u0646\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: 12,13,14</i>",
        parse_mode="HTML")


@router.message(SPState.multi_status)
async def sp_multi_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    await state.clear()
    try:
        ids = [int(x.strip()) for x in (msg.text or "").split(",") if x.strip().isdigit()]
        if not ids:
            await msg.answer("\u274c \u0634\u0646\u0627\u0633\u0647\u200c\u0647\u0627 \u0635\u062d\u06cc\u062d \u0646\u06cc\u0633\u062a."); return
        from services.smmpass import get_orders_status
        raw = await get_orders_status(ids)
        lines = []
        for oid, d in raw.items():
            if isinstance(d, dict):
                icon = _status_icon(str(d.get("status", "")))
                lines.append(
                    f"{icon} <b>#{oid}</b>: {d.get('status','?')} | "
                    f"${d.get('charge','?')} | \u0628\u0627\u0642\u06cc: {d.get('remains','?')}"
                )
            else:
                lines.append(f"\u274c <b>#{oid}</b>: {d}")
        await msg.answer(
            "\U0001f4ca <b>\u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627</b>\n\n" + "\n".join(lines),
            reply_markup=sp_main_menu(), parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"\u274c <code>{str(e)[:120]}</code>",
                         reply_markup=sp_main_menu(), parse_mode="HTML")
