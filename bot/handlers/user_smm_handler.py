"""
User SMM handler - browse categories, services, place orders with markup.
"""
import hashlib
import logging
from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from services.user_service import get_user, get_setting
from services.order_service import get_markup, apply_markup, place_order

logger   = logging.getLogger("user_smm")
router   = Router()
PAGE_SIZE = 8
CAT_PAGE  = 8

_cat_map: dict[str, str] = {}

def _ch(cat: str) -> str:
    h = hashlib.md5(cat.encode()).hexdigest()[:8]
    _cat_map[h] = cat
    return h

def _cn(h: str) -> str:
    return _cat_map.get(h, h)

def _cat_icon(cat: str) -> str:
    c = cat.lower()
    if "instagram" in c: return "📸"
    if "telegram"  in c: return "📨"
    if "youtube"   in c: return "🎥"
    if "tiktok"    in c: return "🎵"
    if "twitter"   in c: return "🐦"
    if "facebook"  in c: return "🇫"
    if "spotify"   in c: return "🎶"
    if "linkedin"  in c: return "💼"
    if "discord"   in c: return "🎮"
    if "twitch"    in c: return "🎮"
    return "🔹"

def _type_icon(t: str) -> str:
    return {
        "default": "📦", "package": "🎁",
        "custom comments": "💬", "subscriptions": "🔄",
        "mentions with hashtags": "🏷",
    }.get(t.lower(), "🔹")


class USMMState(StatesGroup):
    search      = State()
    order_link  = State()
    order_qty   = State()
    order_extra = State()


# ─── Categories ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("u_smm_cats_"))
async def u_smm_cats(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    msg  = await cb.message.edit_text("⏳ \u062f\u0631 \u062d\u0627\u0644 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc...", parse_mode="HTML")
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        if not svcs:
            await msg.edit_text("❌ \u0633\u0631\u0648\u06cc\u0633\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.",
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
                                ]))
            return

        cat_count: dict[str, int] = {}
        for s in svcs:
            cat_count[s["category"]] = cat_count.get(s["category"], 0) + 1
        cats  = list(cat_count.keys())
        for c in cats: _ch(c)

        total = len(cats)
        start = page * CAT_PAGE
        end   = start + CAT_PAGE
        pages = max(1, (total + CAT_PAGE - 1) // CAT_PAGE)

        async with AsyncSessionLocal() as session:
            markup = await get_markup(session)

        rows = []
        for cat in cats[start:end]:
            h     = _ch(cat)
            icon  = _cat_icon(cat)
            count = cat_count[cat]
            name  = cat[:30] + "…" if len(cat) > 30 else cat
            rows.append([InlineKeyboardButton(
                text=f"{icon} {name} ({count})",
                callback_data=f"u_smm_cat_{h}_0"
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"u_smm_cats_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="u_noop"))
        if end < total:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"u_smm_cats_{page+1}"))
        if nav: rows.append(nav)
        rows.append([InlineKeyboardButton(text="🔍 \u062c\u0633\u062a\u062c\u0648", callback_data="u_smm_search")])
        rows.append([InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")])

        await msg.edit_text(
            f"📊 <b>\u062e\u062f\u0645\u0627\u062a SMM</b>\n"
            f"📈 Markup: +{markup:.0f}% | {total} \u062f\u0633\u062a\u0647 | {len(svcs)} \u0633\u0631\u0648\u06cc\u0633\n"
            "\u06cc\u06a9 \u062f\u0633\u062a\u0647 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ <code>{str(e)[:200]}</code>",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
                            ]), parse_mode="HTML")


@router.callback_query(F.data == "u_noop")
async def u_noop(cb: CallbackQuery):
    await cb.answer()


# ─── Services in category ──────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("u_smm_cat_"))
async def u_smm_cat(cb: CallbackQuery):
    await cb.answer()
    parts    = cb.data.split("_")   # ["u","smm","cat",hash,page]
    cat_hash = parts[3]
    page     = int(parts[4])
    cat_name = _cn(cat_hash)

    msg = await cb.message.edit_text("⏳ \u062f\u0631 \u062d\u0627\u0644 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc...", parse_mode="HTML")
    try:
        from services.smmpass import get_services
        all_svcs = await get_services()
        for s in all_svcs: _ch(s["category"])
        svcs  = [s for s in all_svcs if s["category"] == cat_name]
        total = len(svcs)
        start = page * PAGE_SIZE
        end   = start + PAGE_SIZE
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        async with AsyncSessionLocal() as session:
            markup = await get_markup(session)

        rows = []
        for s in svcs[start:end]:
            icon      = _type_icon(s["type"])
            user_rate = apply_markup(float(s["rate"]), markup)
            df        = " 🔄" if s["dripfeed"] else ""
            name      = s['name'][:26] + "…" if len(s['name']) > 26 else s['name']
            rows.append([InlineKeyboardButton(
                text=f"{icon} [{s['service']}] {name}{df} | ${user_rate:.4f}",
                callback_data=f"u_smm_svc_{s['service']}"
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"u_smm_cat_{cat_hash}_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="u_noop"))
        if end < total:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"u_smm_cat_{cat_hash}_{page+1}"))
        if nav: rows.append(nav)
        rows.append([InlineKeyboardButton(text="🔙 \u062f\u0633\u062a\u0647\u200c\u0628\u0646\u062f\u06cc", callback_data="u_smm_cats_0")])
        rows.append([InlineKeyboardButton(text="🏠 \u0645\u0646\u0648", callback_data="u_menu")])

        cat_short = cat_name[:40] + "…" if len(cat_name) > 40 else cat_name
        await msg.edit_text(
            f"{_cat_icon(cat_name)} <b>{cat_short}</b>\n"
            f"📊 {total} \u0633\u0631\u0648\u06cc\u0633 | \u0642\u06cc\u0645\u062a\u200c\u0647\u0627 \u0628\u0627 markup +{markup:.0f}%\n"
            "\u0631\u0648\u06cc \u0633\u0631\u0648\u06cc\u0633 \u0628\u0632\u0646\u06cc\u062f:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ <code>{str(e)[:200]}</code>",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
                            ]), parse_mode="HTML")


# ─── Service detail ─────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("u_smm_svc_"))
async def u_smm_svc(cb: CallbackQuery):
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        svc  = next((s for s in svcs if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("❌ \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True); return

        async with AsyncSessionLocal() as session:
            markup    = await get_markup(session)
            user      = await get_user(session, cb.from_user.id)
            user_bal  = float(user.balance) if user else 0

        user_rate = apply_markup(float(svc["rate"]), markup)
        min_cost  = round(user_rate * int(svc["min"]) / 1000, 4)
        cat_h     = _ch(svc["category"])
        drip      = "✅" if svc["dripfeed"] else "❌"

        text = (
            f"{_type_icon(svc['type'])} <b>{svc['name']}</b>\n\n"
            f"🏷 <i>{svc['category'][:50]}</i>\n"
            f"🔢 ID: <code>{svc['service']}</code>\n"
            f"💰 \u0642\u06cc\u0645\u062a: <b>${user_rate:.4f}</b> / 1000\n"
            f"📉 \u062d\u062f\u0627\u0642\u0644: <b>{svc['min']}</b> | "
            f"📈 \u062d\u062f\u0627\u06a9\u062b\u0631: <b>{svc['max']}</b>\n"
            f"💳 \u06a9\u0645\u062a\u0631\u06cc\u0646 \u0633\u0641\u0627\u0631\u0634: <b>${min_cost:.4f}</b>\n"
            f"🔄 Drip-feed: {drip}\n"
            f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc \u0634\u0645\u0627: <b>${user_bal:.4f}</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"➕ \u062b\u0628\u062a \u0633\u0641\u0627\u0631\u0634",
                callback_data=f"u_smm_order_{svc_id}"
            )],
            [InlineKeyboardButton(text="🔙 \u0628\u0631\u06af\u0634\u062a \u0628\u0647 \u062f\u0633\u062a\u0647",
                                  callback_data=f"u_smm_cat_{cat_h}_0")],
            [InlineKeyboardButton(text="🏠 \u0645\u0646\u0648", callback_data="u_menu")],
        ])
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)


# ─── Search ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "u_smm_search")
async def u_smm_search_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(USMMState.search)
    await cb.message.edit_text(
        "🔍 <b>\u062c\u0633\u062a\u062c\u0648 \u062f\u0631 \u062e\u062f\u0645\u0627\u062a</b>\n\n"
        "\u0646\u0627\u0645 \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627 \u062f\u0633\u062a\u0647 \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: instagram followers, telegram views</i>",
        parse_mode="HTML")


@router.message(USMMState.search)
async def u_smm_search_handle(msg: Message, state: FSMContext):
    q = (msg.text or "").strip().lower()
    await state.clear()
    try:
        from services.smmpass import get_services
        svcs    = await get_services()
        results = [s for s in svcs
                   if q in s["name"].lower() or q in s["category"].lower()
                   or q == str(s["service"])]
        if not results:
            await msg.answer(f"❌ \u0646\u062a\u06cc\u062c\u0647\u200c\u0627\u06cc \u0628\u0631\u0627\u06cc '<b>{q}</b>' \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                 [InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")]
                             ]), parse_mode="HTML"); return

        async with AsyncSessionLocal() as session:
            markup = await get_markup(session)

        rows = []
        for s in results[:20]:
            icon      = _type_icon(s["type"])
            user_rate = apply_markup(float(s["rate"]), markup)
            name      = s['name'][:26] + "…" if len(s['name']) > 26 else s['name']
            rows.append([InlineKeyboardButton(
                text=f"{icon} [{s['service']}] {name} | ${user_rate:.4f}",
                callback_data=f"u_smm_svc_{s['service']}"
            )])
        rows.append([InlineKeyboardButton(text="🔙 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="u_menu")])
        suffix = " (\u0627\u0648\u0644 20)" if len(results) > 20 else ""
        await msg.answer(
            f"🔍 '<b>{q}</b>': <b>{len(results)}</b> \u0633\u0631\u0648\u06cc\u0633{suffix}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")


# ─── Order flow ──────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("u_smm_order_"))
async def u_smm_order_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        svc  = next((s for s in svcs if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("❌ \u0633\u0631\u0648\u06cc\u0633 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f.", show_alert=True); return

        async with AsyncSessionLocal() as session:
            user   = await get_user(session, cb.from_user.id)
            markup = await get_markup(session)

        if not user:
            await cb.answer("❌ \u0627\u0628\u062a\u062f\u0627 /start \u0628\u0632\u0646\u06cc\u062f.", show_alert=True); return

        user_rate = apply_markup(float(svc["rate"]), markup)
        await state.update_data(u_svc=svc, u_svc_id=svc_id, u_markup=markup)

        t = svc["type"].lower()
        if t == "subscriptions":
            await state.set_state(USMMState.order_extra)
            await state.update_data(u_extra_type="sub_username")
            await cb.message.edit_text(
                f"🔄 <b>Subscription [{svc_id}]</b>\n"
                f"💰 \u0642\u06cc\u0645\u062a: ${user_rate:.4f} / 1000\n\n"
                "👤 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:",
                parse_mode="HTML")
        elif t in ("custom comments", "custom comments package"):
            await state.set_state(USMMState.order_link)
            await state.update_data(u_next="comments")
            await cb.message.edit_text(
                f"💬 <b>Custom Comments [{svc_id}]</b>\n\n"
                "🔗 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
        else:
            await state.set_state(USMMState.order_link)
            await state.update_data(u_next="default")
            await cb.message.edit_text(
                f"📦 <b>[{svc_id}] {svc['name']}</b>\n\n"
                f"💰 \u0642\u06cc\u0645\u062a: ${user_rate:.4f} / 1000\n"
                f"📉 \u062d\u062f\u0627\u0642\u0644: {svc['min']} | 📈 \u062d\u062f\u0627\u06a9\u062b\u0631: {svc['max']}\n\n"
                "🔗 \u0644\u06cc\u0646\u06a9 \u0635\u0641\u062d\u0647 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
                parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)


@router.message(USMMState.order_link)
async def u_order_link(msg: Message, state: FSMContext):
    link = (msg.text or "").strip()
    if not link.startswith("http"):
        await msg.answer("❌ \u0644\u06cc\u0646\u06a9 \u0645\u0639\u062a\u0628\u0631 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    data = await state.get_data()
    await state.update_data(u_link=link)
    svc  = data.get("u_svc", {})
    nxt  = data.get("u_next", "default")
    if nxt == "comments":
        await state.set_state(USMMState.order_extra)
        await state.update_data(u_extra_type="comments")
        await msg.answer("💬 \u06a9\u0627\u0645\u0646\u062a\u200c\u0647\u0627 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f (\u0647\u0631 \u062e\u0637 \u06cc\u06a9 \u06a9\u0627\u0645\u0646\u062a):")
    else:
        await state.set_state(USMMState.order_qty)
        await msg.answer(f"🔢 \u062a\u0639\u062f\u0627\u062f (\u062d\u062f\u0627\u0642\u0644 {svc.get('min','?')} | \u062d\u062f\u0627\u06a9\u062b\u0631 {svc.get('max','?')}):")


@router.message(USMMState.order_qty)
async def u_order_qty(msg: Message, state: FSMContext):
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("❌ \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return

    data = await state.get_data()
    svc  = data["u_svc"]
    link = data["u_link"]
    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await get_user(session, msg.from_user.id)
        if not user: return
        try:
            result = await place_order(session, user.id, svc, link, qty)
            await session.commit()
            await msg.answer(
                f"✅ <b>\u0633\u0641\u0627\u0631\u0634 \u062b\u0628\u062a \u0634\u062f!</b>\n\n"
                f"📦 \u0634\u0646\u0627\u0633\u0647 \u062f\u0627\u062e\u0644\u06cc: <code>{result['order_id']}</code>\n"
                f"💰 \u0647\u0632\u06cc\u0646\u0647: <b>${result['charge']:.4f}</b>\n"
                f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc \u0628\u0627\u0642\u06cc\u0645\u0627\u0646\u062f\u0647: <b>${float(user.balance) - result['charge']:.4f}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627\u06cc \u0645\u0646", callback_data="u_my_orders")],
                    [InlineKeyboardButton(text="🏠 \u0645\u0646\u0648", callback_data="u_menu")],
                ]),
                parse_mode="HTML"
            )
        except ValueError as e:
            if "insufficient" in str(e):
                await msg.answer(
                    "❌ <b>\u0645\u0648\u062c\u0648\u062f\u06cc \u06a9\u0627\u0641\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f.</b>\n"
                    "\u0627\u0628\u062a\u062f\u0627 \u062d\u0633\u0627\u0628\u062a\u0627\u0646 \u0631\u0627 \u0634\u0627\u0631\u0698 \u06a9\u0646\u06cc\u062f.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💰 \u0634\u0627\u0631\u0698 \u062d\u0633\u0627\u0628", callback_data="u_deposit")],
                        [InlineKeyboardButton(text="🏠 \u0645\u0646\u0648", callback_data="u_menu")],
                    ]),
                    parse_mode="HTML"
                )
            else:
                await msg.answer(f"❌ {str(e)[:200]}", parse_mode="HTML")
        except Exception as e:
            await msg.answer(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")


@router.message(USMMState.order_extra)
async def u_order_extra(msg: Message, state: FSMContext):
    extra = (msg.text or "").strip()
    data  = await state.get_data()
    et    = data.get("u_extra_type", "")
    svc   = data["u_svc"]
    link  = data.get("u_link", "")
    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await get_user(session, msg.from_user.id)
        if not user: return
        try:
            if et == "comments":
                result = await place_order(session, user.id, svc, link, 0, {"comments": extra})
            elif et == "sub_username":
                result = await place_order(session, user.id, svc, "", 0,
                                           {"username": extra, "min": int(svc.get("min", 1)), "max": int(svc.get("max", 100))})
            else:
                await msg.answer("❌ \u0646\u0648\u0639 \u0633\u0641\u0627\u0631\u0634 \u0646\u0627\u0645\u0634\u062e\u0635."); return
            await session.commit()
            await msg.answer(
                f"✅ <b>\u0633\u0641\u0627\u0631\u0634 \u062b\u0628\u062a \u0634\u062f!</b>\n"
                f"📦 \u0634\u0646\u0627\u0633\u0647: <code>{result['order_id']}</code>\n"
                f"💰 \u0647\u0632\u06cc\u0646\u0647: <b>${result['charge']:.4f}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 \u0645\u0646\u0648", callback_data="u_menu")]
                ]),
                parse_mode="HTML"
            )
        except ValueError as e:
            if "insufficient" in str(e):
                await msg.answer("❌ \u0645\u0648\u062c\u0648\u062f\u06cc \u06a9\u0627\u0641\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f.",
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="💰 \u0634\u0627\u0631\u0698 \u062d\u0633\u0627\u0628", callback_data="u_deposit")]
                                 ]))
            else:
                await msg.answer(f"❌ {str(e)[:200]}")
        except Exception as e:
            await msg.answer(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")
