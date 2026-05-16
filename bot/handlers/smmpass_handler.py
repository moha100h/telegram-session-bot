"""
SMMPass user panel handler.
- Categories -> paginated service list -> service detail -> order flow
- Balance check & deduction before placing order
- Markup applied from settings (smm_markup_percent)
- db_user injected by AuthMiddleware
"""
import hashlib
import logging
import math

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db.database import AsyncSessionLocal
from db.models import User
from services.smmpass import (
    get_services, get_balance,
    add_order_default, add_order_package,
    add_order_mentions_hashtag, add_order_mentions_custom,
    add_order_custom_comments, add_order_subscription,
    get_order_status, clear_cache,
)
from services.user_service import get_setting, deduct_balance, add_balance
from services.order_service import create_order

logger   = logging.getLogger("smmpass_user")
router   = Router()

PAGE_SVC = 8
PAGE_CAT = 6

_cat_map: dict = {}

def _ch(cat: str) -> str:
    h = hashlib.md5(cat.encode()).hexdigest()[:8]
    _cat_map[h] = cat
    return h

def _cn(h: str) -> str:
    return _cat_map.get(h, h)


class SPState(StatesGroup):
    order_link   = State()
    order_qty    = State()
    order_extra  = State()
    order_status = State()
    sub_username = State()
    sub_min      = State()
    sub_max      = State()


def _status_icon(s: str) -> str:
    s = s.lower()
    if any(x in s for x in ("complet", "done", "finish")): return "\u2705"
    if any(x in s for x in ("pending", "process", "progress", "active")): return "\u23f3"
    if any(x in s for x in ("cancel", "fail", "error")): return "\u274c"
    if "partial" in s: return "\u26a0\ufe0f"
    return "\U0001f7e1"

def _type_label(t: str) -> str:
    return {
        "default":            "\u067e\u06cc\u0634\u200c\u0641\u0631\u0636",
        "package":            "\u067e\u06a9\u06cc\u062c",
        "custom_comments":    "\u06a9\u0627\u0645\u0646\u062a \u062f\u0644\u062e\u0648\u0627\u0647",
        "mentions_hashtag":   "\u0645\u0646\u0634\u0646 \u0647\u0634\u062a\u06af",
        "mentions_custom":    "\u0645\u0646\u0634\u0646 \u062f\u0644\u062e\u0648\u0627\u0647",
        "mentions_hashtags":  "\u0645\u0646\u0634\u0646 \u0647\u0634\u062a\u06af",
        "mentions_followers": "\u0645\u0646\u0634\u0646 \u0641\u0627\u0644\u0648\u0648\u0631",
        "comment_likes":      "\u0644\u0627\u06cc\u06a9 \u06a9\u0627\u0645\u0646\u062a",
        "subscription":       "\u0627\u0634\u062a\u0631\u0627\u06a9",
        "poll":               "\u0646\u0638\u0631\u0633\u0646\u062c\u06cc",
    }.get(t, t)

def _cat_icon(cat: str) -> str:
    c = cat.lower()
    if "member" in c:   return "\U0001f4e2"
    if "view" in c:     return "\U0001f440"
    if "reaction" in c: return "\U0001f44d"
    if "share" in c:    return "\U0001f4e4"
    if "story" in c:    return "\U0001f4f8"
    if "bot" in c:      return "\U0001f916"
    if "activity" in c: return "\U0001f9e0"
    if "ads" in c:      return "\U0001f4e3"
    if "growth" in c:   return "\U0001f4c8"
    if "vote" in c:     return "\U0001f5f3"
    if "free" in c:     return "\U0001f381"
    if "spotify" in c:  return "\U0001f3b5"
    return "\U0001f4cc"

async def _get_markup(session) -> float:
    val = await get_setting(session, "smm_markup_percent", "20")
    try:
        return float(val)
    except Exception:
        return 20.0

def _sell_rate(rate: float, markup: float) -> float:
    return round(rate * (1 + markup / 100), 6)

def _order_total(sell_rate: float, qty: int) -> float:
    return round(sell_rate * qty / 1000, 6)


# Entry
@router.callback_query(F.data == "menu_smmpass")
async def sp_entry(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await state.clear()
    await cb.answer()
    async with AsyncSessionLocal() as session:
        markup = await _get_markup(session)
    services = await get_services()
    bal = float(db_user.balance or 0) if db_user else 0
    await cb.message.edit_text(
        f"\U0001f680 <b>\u067e\u0646\u0644 SMMPass</b>\n\n"
        f"\U0001f4b0 \u0645\u0648\u062c\u0648\u062f\u06cc \u0634\u0645\u0627: <b>${bal:.4f}</b>\n"
        f"\U0001f4ca \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627: <b>{len(services)}</b>\n"
        f"\U0001f4b9 \u0633\u0648\u062f \u0627\u0639\u0645\u0627\u0644\u200c\u0634\u062f\u0647: <b>{markup:.0f}%</b>\n\n"
        "\u06cc\u06a9 \u0628\u062e\u0634 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4cb \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627", callback_data="sp_cats_0")],
            [InlineKeyboardButton(text="\U0001f4e6 \u0633\u0641\u0627\u0631\u0634\u0627\u062a \u0645\u0646", callback_data="sp_my_orders")],
            [InlineKeyboardButton(text="\U0001f50d \u0648\u0636\u0639\u06cc\u062a \u0633\u0641\u0627\u0631\u0634", callback_data="sp_order_status")],
            [InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


# Categories paginated
@router.callback_query(F.data.startswith("sp_cats_"))
async def sp_cats_page(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        markup = await _get_markup(session)
    services = await get_services()
    cats = {}
    for s in services:
        cat = s.get("category", "Other")
        if cat not in cats:
            cats[cat] = {"count": 0, "min_r": float("inf")}
        cats[cat]["count"] += 1
        r = float(s.get("rate", 0))
        cats[cat]["min_r"] = min(cats[cat]["min_r"], r)
    cat_list = sorted(cats.items(), key=lambda x: -x[1]["count"])
    total_pages = max(1, math.ceil(len(cat_list) / PAGE_CAT))
    page = max(0, min(page, total_pages - 1))
    page_cats = cat_list[page * PAGE_CAT:(page + 1) * PAGE_CAT]
    buttons = []
    for cat, info in page_cats:
        icon = _cat_icon(cat)
        short = cat.replace("TG - ", "")[:28]
        sell = _sell_rate(info["min_r"], markup)
        h = _ch(cat)
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {short} ({info['count']}) | \u0627\u0632 ${sell:.4f}",
            callback_data=f"sp_cat_{h}_0"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05 \u0642\u0628\u0644\u06cc", callback_data=f"sp_cats_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="\u0628\u0639\u062f\u06cc \u27a1", callback_data=f"sp_cats_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_smmpass")])
    await cb.message.edit_text(
        f"\U0001f4cb <b>\u062f\u0633\u062a\u0647\u200c\u0628\u0646\u062f\u06cc\u200c\u0647\u0627</b> \u2014 \u0635\u0641\u062d\u0647 {page+1}/{total_pages}\n\n"
        "\u06cc\u06a9 \u062f\u0633\u062a\u0647 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


# Services in category
@router.callback_query(F.data.startswith("sp_cat_"))
async def sp_cat_svcs(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split("_")
    cat_hash = parts[2]
    page = int(parts[3])
    cat = _cn(cat_hash)
    if not cat or cat == cat_hash:
        await cb.answer("\u062f\u0633\u062a\u0647 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f!", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        markup = await _get_markup(session)
    services = await get_services()
    cat_svcs = [s for s in services if s.get("category") == cat]
    total_pages = max(1, math.ceil(len(cat_svcs) / PAGE_SVC))
    page = max(0, min(page, total_pages - 1))
    page_svcs = cat_svcs[page * PAGE_SVC:(page + 1) * PAGE_SVC]
    buttons = []
    for s in page_svcs:
        sell = _sell_rate(float(s.get("rate", 0)), markup)
        name = s["name"][:32]
        buttons.append([InlineKeyboardButton(
            text=f"{name} | ${sell:.4f}/1K",
            callback_data=f"sp_svc_{s['service']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="\u2b05", callback_data=f"sp_cat_{cat_hash}_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="\u27a1", callback_data=f"sp_cat_{cat_hash}_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="\U0001f519 \u062f\u0633\u062a\u0647\u200c\u0628\u0646\u062f\u06cc\u200c\u0647\u0627", callback_data="sp_cats_0")])
    short = cat.replace("TG - ", "")[:35]
    await cb.message.edit_text(
        f"\U0001f4cc <b>{short}</b>\n"
        f"\u0635\u0641\u062d\u0647 {page+1}/{total_pages} | {len(cat_svcs)} \u0633\u0631\u0648\u06cc\u0633\n\n"
        "\u06cc\u06a9 \u0633\u0631\u0648\u06cc\u0633 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


# Service detail
@router.callback_query(F.data.startswith("sp_svc_"))
async def sp_svc_detail(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await cb.answer()
    svc_id = cb.data[7:]
    services = await get_services()
    svc = next((s for s in services if str(s["service"]) == str(svc_id)), None)
    if not svc:
        await cb.answer("\u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f!", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        markup = await _get_markup(session)
    base_rate = float(svc.get("rate", 0))
    sell = _sell_rate(base_rate, markup)
    min_q = int(svc.get("min", 1))
    max_q = int(svc.get("max", 1000000))
    svc_type = svc.get("type", "default")
    desc = (svc.get("desc") or "")[:200]
    bal = float(db_user.balance or 0) if db_user else 0
    await state.update_data(
        sp_svc_id=str(svc_id),
        sp_svc_name=svc["name"],
        sp_svc_rate=sell,
        sp_base_rate=base_rate,
        sp_svc_min=min_q,
        sp_svc_max=max_q,
        sp_svc_type=svc_type,
    )
    text = (
        f"\U0001f4cc <b>{svc['name']}</b>\n\n"
        f"\U0001f4b0 \u0642\u06cc\u0645\u062a: <b>${sell:.4f}</b> / 1K\n"
        f"\U0001f522 \u062d\u062f\u0627\u0642\u0644: <b>{min_q:,}</b> | \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{max_q:,}</b>\n"
        f"\U0001f527 \u0646\u0648\u0639: <b>{_type_label(svc_type)}</b>\n"
        f"\U0001f4b3 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal:.4f}</b>\n"
    )
    if desc:
        text += f"\n\U0001f4dd {desc}\n"
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2705 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634", callback_data=f"sp_order_{svc_id}")],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="sp_cats_0")],
        ]),
        parse_mode="HTML"
    )


# Order start
@router.callback_query(F.data.startswith("sp_order_"))
async def sp_order_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    svc_type = data.get("sp_svc_type", "default")
    if svc_type == "subscription":
        await state.set_state(SPState.sub_username)
        await cb.message.edit_text("\U0001f4cc \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u06a9\u0627\u0646\u0627\u0644/\u06af\u0631\u0648\u0647 (\u0628\u062f\u0648\u0646 @):\n\n/cancel \u0644\u063a\u0648")
        return
    if svc_type == "package":
        await state.set_state(SPState.order_link)
        await cb.message.edit_text("\U0001f517 \u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u06cc\u0627 \u06a9\u0627\u0646\u0627\u0644:\n\n/cancel \u0644\u063a\u0648")
        return
    await state.set_state(SPState.order_link)
    hints = {
        "poll":             "\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u0646\u0638\u0631\u0633\u0646\u062c\u06cc",
        "mentions_hashtag": "\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u062a\u0644\u06af\u0631\u0627\u0645",
        "mentions_custom":  "\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u062a\u0644\u06af\u0631\u0627\u0645",
        "custom_comments":  "\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u062a\u0644\u06af\u0631\u0627\u0645",
        "comment_likes":    "\u0644\u06cc\u0646\u06a9 \u06a9\u0627\u0645\u0646\u062a",
    }
    hint = hints.get(svc_type, "\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u06cc\u0627 \u06a9\u0627\u0646\u0627\u0644 \u062a\u0644\u06af\u0631\u0627\u0645")
    await cb.message.edit_text(f"\U0001f517 <b>\u0644\u06cc\u0646\u06a9 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:</b>\n{hint}\n\n/cancel \u0644\u063a\u0648", parse_mode="HTML")


@router.message(SPState.order_link)
async def sp_order_link(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    link = (msg.text or "").strip()
    if not link:
        await msg.answer("\u274c \u0644\u06cc\u0646\u06a9 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.update_data(sp_link=link)
    data = await state.get_data()
    svc_type = data.get("sp_svc_type", "default")
    if svc_type == "package":
        await _finalize_package(msg, state); return
    if svc_type in ("custom_comments", "mentions_custom"):
        await state.set_state(SPState.order_extra)
        label = "\u06a9\u0627\u0645\u0646\u062a\u200c\u0647\u0627 (\u0647\u0631 \u062e\u0637 \u06cc\u06a9 \u06a9\u0627\u0645\u0646\u062a)" if svc_type == "custom_comments" else "\u06cc\u0648\u0632\u0631\u0646\u06cc\u0645\u200c\u0647\u0627 (\u0647\u0631 \u062e\u0637 \u06cc\u06a9)"
        await msg.answer(f"\u270f\ufe0f {label}:\n\n/cancel \u0644\u063a\u0648"); return
    await state.set_state(SPState.order_qty)
    min_q = data.get("sp_svc_min", 1)
    max_q = data.get("sp_svc_max", 1000000)
    sell = data.get("sp_svc_rate", 0)
    await msg.answer(
        f"\U0001f522 <b>\u062a\u0639\u062f\u0627\u062f \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:</b>\n"
        f"\u062d\u062f\u0627\u0642\u0644: <b>{min_q:,}</b> | \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{max_q:,}</b>\n"
        f"\U0001f4b0 \u0642\u06cc\u0645\u062a: <b>${sell:.4f}</b>/1K\n\n/cancel \u0644\u063a\u0648",
        parse_mode="HTML"
    )


@router.message(SPState.order_extra)
async def sp_order_extra(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    await state.update_data(sp_extra=msg.text.strip())
    await state.set_state(SPState.order_qty)
    data = await state.get_data()
    min_q = data.get("sp_svc_min", 1); max_q = data.get("sp_svc_max", 1000000)
    await msg.answer(f"\U0001f522 \u062a\u0639\u062f\u0627\u062f:\n\u062d\u062f\u0627\u0642\u0644: <b>{min_q:,}</b> | \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{max_q:,}</b>\n\n/cancel \u0644\u063a\u0648", parse_mode="HTML")


@router.message(SPState.order_qty)
async def sp_order_qty(msg: Message, state: FSMContext, db_user: User = None):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    try:
        qty = int((msg.text or "").strip().replace(",", ""))
    except ValueError:
        await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    min_q = data.get("sp_svc_min", 1); max_q = data.get("sp_svc_max", 1000000)
    if qty < min_q or qty > max_q:
        await msg.answer(f"\u274c \u062a\u0639\u062f\u0627\u062f \u0628\u0627\u06cc\u062f \u0628\u06cc\u0646 {min_q:,} \u0648 {max_q:,} \u0628\u0627\u0634\u062f."); return
    sell_rate = data.get("sp_svc_rate", 0)
    total = _order_total(sell_rate, qty)
    bal = float(db_user.balance or 0) if db_user else 0
    await state.update_data(sp_qty=qty, sp_total=total)
    bal_ok = bal >= total
    rows = [
        [InlineKeyboardButton(text="\u274c \u0644\u063a\u0648", callback_data="sp_cancel")],
    ]
    if bal_ok:
        rows.insert(0, [InlineKeyboardButton(text="\u2705 \u062a\u0627\u06cc\u06cc\u062f \u0648 \u067e\u0631\u062f\u0627\u062e\u062a", callback_data="sp_confirm")])
    else:
        rows.insert(0, [InlineKeyboardButton(text="\U0001f4b3 \u0634\u0627\u0631\u0698 \u0645\u0648\u062c\u0648\u062f\u06cc", callback_data="user_deposit")])
    await msg.answer(
        f"\U0001f4cb <b>\u062a\u0627\u06cc\u06cc\u062f \u0633\u0641\u0627\u0631\u0634</b>\n\n"
        f"\U0001f4cc \u0633\u0631\u0648\u06cc\u0633: <b>{data.get('sp_svc_name','')[:40]}</b>\n"
        f"\U0001f517 \u0644\u06cc\u0646\u06a9: <code>{data.get('sp_link','')}</code>\n"
        f"\U0001f522 \u062a\u0639\u062f\u0627\u062f: <b>{qty:,}</b>\n"
        f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>${total:.4f}</b>\n"
        f"\U0001f4b3 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal:.4f}</b>\n\n"
        f"{'\u2705 \u0645\u0648\u062c\u0648\u062f\u06cc \u06a9\u0627\u0641\u06cc \u0627\u0633\u062a' if bal_ok else '\u274c \u0645\u0648\u062c\u0648\u062f\u06cc \u0646\u0627\u06a9\u0627\u0641\u06cc \u2014 \u0627\u0628\u062a\u062f\u0627 \u0634\u0627\u0631\u0698 \u06a9\u0646\u06cc\u062f'}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


async def _finalize_package(msg: Message, state: FSMContext):
    data = await state.get_data()
    svc_id = data.get("sp_svc_id"); link = data.get("sp_link","")
    svc_name = data.get("sp_svc_name",""); sell_rate = data.get("sp_svc_rate",0)
    total = round(sell_rate / 1000, 6)
    await state.update_data(sp_qty=1, sp_total=total)
    await msg.answer(
        f"\U0001f4cb \u067e\u06a9\u06cc\u062c: <b>{svc_name[:40]}</b>\n\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>${total:.4f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u2705 \u062a\u0627\u06cc\u06cc\u062f", callback_data="sp_confirm")],
            [InlineKeyboardButton(text="\u274c \u0644\u063a\u0648", callback_data="sp_cancel")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "sp_confirm")
async def sp_confirm(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await cb.answer()
    data = await state.get_data()
    svc_id    = data.get("sp_svc_id")
    svc_name  = data.get("sp_svc_name", "")
    link      = data.get("sp_link", "")
    qty       = data.get("sp_qty", 0)
    total     = data.get("sp_total", 0)
    sell_rate = data.get("sp_svc_rate", 0)
    base_rate = data.get("sp_base_rate", 0)
    svc_type  = data.get("sp_svc_type", "default")
    extra     = data.get("sp_extra", "")
    bal = float(db_user.balance or 0) if db_user else 0
    if bal < total:
        await cb.message.edit_text(
            "\u274c <b>\u0645\u0648\u062c\u0648\u062f\u06cc \u0646\u0627\u06a9\u0627\u0641\u06cc!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f4b3 \u0634\u0627\u0631\u0698", callback_data="user_deposit")],
                [InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="user_home")],
            ]),
            parse_mode="HTML"
        ); return
    await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634...")
    async with AsyncSessionLocal() as session:
        ok = await deduct_balance(session, db_user.id, total)
        if not ok:
            await cb.message.edit_text("\u274c \u062e\u0637\u0627 \u062f\u0631 \u06a9\u0633\u0631 \u0645\u0648\u062c\u0648\u062f\u06cc."); return
        await session.commit()
        try:
            if svc_type == "package":
                result = await add_order_package(int(svc_id), link)
            elif svc_type == "custom_comments":
                result = await add_order_custom_comments(int(svc_id), link, extra)
            elif svc_type == "mentions_custom":
                result = await add_order_mentions_custom(int(svc_id), link, extra)
            elif svc_type == "mentions_hashtag":
                result = await add_order_mentions_hashtag(int(svc_id), link, qty)
            else:
                result = await add_order_default(int(svc_id), link, qty)
            ext_id = str(result.get("order", ""))
        except Exception as e:
            await add_balance(session, db_user.id, total)
            await session.commit()
            await cb.message.edit_text(f"\u274c \u062e\u0637\u0627 API:\n<code>{e}</code>", parse_mode="HTML"); return
        order = await create_order(
            session, user_id=db_user.id, service_id=int(svc_id),
            service_name=svc_name, link=link, quantity=qty,
            cost_price=round(base_rate * qty / 1000, 6), sell_price=total,
        )
        await session.commit()
    await state.clear()
    await cb.message.edit_text(
        f"\u2705 <b>\u0633\u0641\u0627\u0631\u0634 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
        f"\U0001f4e6 \u0634\u0646\u0627\u0633\u0647: <b>#{order.id}</b>\n"
        f"\U0001f310 API ID: <code>{ext_id}</code>\n"
        f"\U0001f4b0 \u067e\u0631\u062f\u0627\u062e\u062a: <b>${total:.4f}</b>\n\n"
        "\u23f3 \u0633\u0641\u0627\u0631\u0634 \u062f\u0631 \u062d\u0627\u0644 \u067e\u0631\u062f\u0627\u0632\u0634...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4e6 \u0633\u0641\u0627\u0631\u0634\u0627\u062a \u0645\u0646", callback_data="sp_my_orders")],
            [InlineKeyboardButton(text="\U0001f3e0 \u062e\u0627\u0646\u0647", callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "sp_cancel")
async def sp_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer("\u0644\u063a\u0648 \u0634\u062f.")
    await cb.message.edit_text(
        "\u274c \u0633\u0641\u0627\u0631\u0634 \u0644\u063a\u0648 \u0634\u062f.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_smmpass")]
        ])
    )


# Subscription flow
@router.message(SPState.sub_username)
async def sp_sub_username(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    await state.update_data(sp_link=msg.text.strip().lstrip("@"))
    await state.set_state(SPState.sub_min)
    await msg.answer("\U0001f522 \u062d\u062f\u0627\u0642\u0644 \u062a\u0639\u062f\u0627\u062f \u062f\u0631 \u0631\u0648\u0632:\n\n/cancel \u0644\u063a\u0648")

@router.message(SPState.sub_min)
async def sp_sub_min(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    try: mn = int(msg.text.strip())
    except ValueError: await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d."); return
    await state.update_data(sp_sub_min=mn)
    await state.set_state(SPState.sub_max)
    await msg.answer("\U0001f522 \u062d\u062f\u0627\u06a9\u062b\u0631 \u062a\u0639\u062f\u0627\u062f \u062f\u0631 \u0631\u0648\u0632:\n\n/cancel \u0644\u063a\u0648")

@router.message(SPState.sub_max)
async def sp_sub_max(msg: Message, state: FSMContext, db_user: User = None):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    try: mx = int(msg.text.strip())
    except ValueError: await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d."); return
    data = await state.get_data()
    sell_rate = data.get("sp_svc_rate", 0)
    total = _order_total(sell_rate, mx)
    bal = float(db_user.balance or 0) if db_user else 0
    await state.update_data(sp_qty=mx, sp_total=total)
    bal_ok = bal >= total
    rows = [[InlineKeyboardButton(text="\u274c \u0644\u063a\u0648", callback_data="sp_cancel")]]
    if bal_ok:
        rows.insert(0, [InlineKeyboardButton(text="\u2705 \u062a\u0627\u06cc\u06cc\u062f", callback_data="sp_confirm")])
    else:
        rows.insert(0, [InlineKeyboardButton(text="\U0001f4b3 \u0634\u0627\u0631\u0698", callback_data="user_deposit")])
    await msg.answer(
        f"\U0001f4cb \u0627\u0634\u062a\u0631\u0627\u06a9\n\U0001f464 {data.get('sp_link','')}\n"
        f"\U0001f522 {data.get('sp_sub_min',0):,} \u2013 {mx:,}/\u0631\u0648\u0632\n"
        f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>${total:.4f}</b>\n"
        f"\U0001f4b3 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal:.4f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


# Order status check
@router.callback_query(F.data == "sp_order_status")
async def sp_status_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(SPState.order_status)
    await cb.message.edit_text("\U0001f50d \u0634\u0646\u0627\u0633\u0647 \u0633\u0641\u0627\u0631\u0634 API \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:\n\n/cancel \u0644\u063a\u0648")

@router.message(SPState.order_status)
async def sp_status_handle(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    try: oid = int(msg.text.strip())
    except ValueError: await msg.answer("\u274c \u0634\u0646\u0627\u0633\u0647 \u0639\u062f\u062f\u06cc."); return
    await state.clear()
    try:
        r = await get_order_status(oid)
        status = r.get("status","?"); charge = r.get("charge","?")
        start = r.get("start_count","?"); remains = r.get("remains","?")
        await msg.answer(
            f"\U0001f4e6 <b>\u0633\u0641\u0627\u0631\u0634 #{oid}</b>\n\n"
            f"{_status_icon(str(status))} \u0648\u0636\u0639\u06cc\u062a: <b>{status}</b>\n"
            f"\U0001f4b0 \u0647\u0632\u06cc\u0646\u0647: <b>{charge}</b>\n"
            f"\U0001f522 \u0634\u0631\u0648\u0639: <b>{start}</b> | \u0628\u0627\u0642\u06cc: <b>{remains}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_smmpass")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627: {e}")


# My orders
@router.callback_query(F.data == "sp_my_orders")
async def sp_my_orders(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, db_user.id)
    if not orders:
        await cb.message.edit_text(
            "\U0001f4e6 \u0647\u06cc\u0686 \u0633\u0641\u0627\u0631\u0634\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_smmpass")]
            ])
        ); return
    STATUS_ICON = {"pending":"\u23f3","processing":"\U0001f504","completed":"\u2705","partial":"\u26a0\ufe0f","cancelled":"\u274c","failed":"\U0001f494"}
    lines = []
    for o in orders[:15]:
        icon = STATUS_ICON.get(o.status,"\u2753")
        lines.append(
            f"{icon} <b>#{o.id}</b> | {o.service_name[:22]}\n"
            f"   \U0001f522 {o.quantity:,} | \U0001f4b0 ${float(o.sell_price):.4f} | {o.created_at.strftime('%m/%d %H:%M')}"
        )
    await cb.message.edit_text(
        "\U0001f4e6 <b>\u0633\u0641\u0627\u0631\u0634\u0627\u062a \u0645\u0646</b>\n\n" + "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f3e0 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_smmpass")]
        ]),
        parse_mode="HTML"
    )
