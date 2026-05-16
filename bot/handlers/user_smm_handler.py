"""
User SMM handler - browse categories, services, place orders.
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
from db.models import User
from services.user_service import get_user
from services.settings_service import get_setting
from services.order_service import get_markup, apply_markup, create_order, calc_order_price

logger   = logging.getLogger("user_smm")
router   = Router()
PAGE_SIZE = 8

# category hash map (in-memory)
_cat_map: dict[str, str] = {}

def _ch(cat: str) -> str:
    h = hashlib.md5(cat.encode()).hexdigest()[:8]
    _cat_map[h] = cat
    return h

def _cn(h: str) -> str:
    return _cat_map.get(h, "")

def _cat_icon(cat: str) -> str:
    c = cat.lower()
    icons = {
        "instagram": "📸", "telegram": "📨", "youtube": "🎥",
        "tiktok": "🎵", "twitter": "🐦", "facebook": "🇫",
        "spotify": "🎶", "linkedin": "💼", "discord": "🎮",
        "twitch": "🎮", "snapchat": "👻", "pinterest": "📌",
    }
    for k, v in icons.items():
        if k in c: return v
    return "🔹"


class USMMState(StatesGroup):
    search     = State()
    order_link = State()
    order_qty  = State()
    order_extra= State()


async def show_user_smm_menu(cb: CallbackQuery):
    """Entry point called from user_handler."""
    await _show_cats(cb, 0)


async def _show_cats(cb: CallbackQuery, page: int):
    msg = await cb.message.edit_text("⏳ در حال بارگذاری...")
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        if not svcs:
            await msg.edit_text(
                "❌ سرویسی یافت نشد.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
                ])
            )
            return

        cat_count: dict[str, int] = {}
        for s in svcs:
            cat_count[s["category"]] = cat_count.get(s["category"], 0) + 1
        cats  = list(cat_count.keys())
        for c in cats: _ch(c)

        total = len(cats)
        start = page * PAGE_SIZE
        end   = min(start + PAGE_SIZE, total)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        async with AsyncSessionLocal() as session:
            markup_pct = await get_markup(session)

        rows = []
        for cat in cats[start:end]:
            h    = _ch(cat)
            icon = _cat_icon(cat)
            cnt  = cat_count[cat]
            name = cat[:28] + "…" if len(cat) > 28 else cat
            rows.append([InlineKeyboardButton(
                text=f"{icon} {name} ({cnt})",
                callback_data=f"usmm_cat_{h}_0"
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"usmm_cats_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="usmm_noop"))
        if end < total:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"usmm_cats_{page+1}"))
        if nav: rows.append(nav)
        rows.append([InlineKeyboardButton(text="🔍 جستجو", callback_data="usmm_search")])
        rows.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])

        await msg.edit_text(
            f"📊 <b>خدمات SMM</b>\n"
            f"📈 Markup: +{markup_pct:.0f}% | {total} دسته | {len(svcs)} سرویس\n"
            "یک دسته را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ خطا: <code>{str(e)[:200]}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
            ]),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("usmm_cats_"))
async def usmm_cats(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    await _show_cats(cb, page)


@router.callback_query(F.data == "usmm_noop")
async def usmm_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.startswith("usmm_cat_"))
async def usmm_cat(cb: CallbackQuery):
    await cb.answer()
    parts    = cb.data.split("_")  # usmm_cat_HASH_PAGE
    cat_hash = parts[2]
    page     = int(parts[3])
    cat_name = _cn(cat_hash)

    if not cat_name:
        await cb.answer("❌ دسته یافت نشد. برگردید.", show_alert=True)
        return

    msg = await cb.message.edit_text("⏳ در حال بارگذاری...")
    try:
        from services.smmpass import get_services
        all_svcs = await get_services()
        for s in all_svcs: _ch(s["category"])
        svcs  = [s for s in all_svcs if s["category"] == cat_name]
        total = len(svcs)
        start = page * PAGE_SIZE
        end   = min(start + PAGE_SIZE, total)
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        async with AsyncSessionLocal() as session:
            markup_pct = await get_markup(session)

        rows = []
        for s in svcs[start:end]:
            user_rate = apply_markup(float(s["rate"]), markup_pct)
            name = s['name'][:24] + "…" if len(s['name']) > 24 else s['name']
            rows.append([InlineKeyboardButton(
                text=f"[{s['service']}] {name} | ${user_rate:.4f}",
                callback_data=f"usmm_svc_{s['service']}"
            )])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"usmm_cat_{cat_hash}_{page-1}"))
        nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="usmm_noop"))
        if end < total:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"usmm_cat_{cat_hash}_{page+1}"))
        if nav: rows.append(nav)
        rows.append([InlineKeyboardButton(text="🔙 دسته‌بندی", callback_data="usmm_cats_0")])
        rows.append([InlineKeyboardButton(text="🏠 منو", callback_data="user_home")])

        cat_short = cat_name[:35] + "…" if len(cat_name) > 35 else cat_name
        await msg.edit_text(
            f"{_cat_icon(cat_name)} <b>{cat_short}</b>\n"
            f"📊 {total} سرویس | +{markup_pct:.0f}% markup\n"
            "روی سرویس بزنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ <code>{str(e)[:200]}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
            ]),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("usmm_svc_"))
async def usmm_svc(cb: CallbackQuery):
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        svc  = next((s for s in svcs if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("❌ سرویس یافت نشد.", show_alert=True)
            return

        async with AsyncSessionLocal() as session:
            markup_pct = await get_markup(session)
            user       = await get_user(session, cb.from_user.id)
            bal        = float(user.balance or 0) if user else 0

        user_rate = apply_markup(float(svc["rate"]), markup_pct)
        min_cost  = round(user_rate * int(svc["min"]) / 1000, 4)
        cat_h     = _ch(svc["category"])

        text = (
            f"📦 <b>{svc['name']}</b>\n\n"
            f"🏷 <i>{svc['category'][:40]}</i>\n"
            f"🔢 ID: <code>{svc['service']}</code>\n"
            f"💰 قیمت: <b>${user_rate:.4f}</b> / 1000\n"
            f"📉 حداقل: <b>{svc['min']}</b> | 📈 حداکثر: <b>{svc['max']}</b>\n"
            f"💳 کمترین سفارش: <b>${min_cost:.4f}</b>\n"
            f"💰 موجودی شما: <b>${bal:.2f}</b>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ ثبت سفارش", callback_data=f"usmm_order_{svc_id}")],
            [InlineKeyboardButton(text="🔙 برگشت به دسته", callback_data=f"usmm_cat_{cat_h}_0")],
            [InlineKeyboardButton(text="🏠 منو", callback_data="user_home")],
        ])
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)


@router.callback_query(F.data.startswith("usmm_order_"))
async def usmm_order_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        from services.smmpass import get_services
        svcs = await get_services()
        svc  = next((s for s in svcs if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("❌ سرویس یافت نشد.", show_alert=True)
            return

        await state.update_data(svc=svc)
        await state.set_state(USMMState.order_link)
        await cb.message.edit_text(
            f"📦 <b>[{svc_id}] {svc['name']}</b>\n\n"
            f"📉 حداقل: {svc['min']} | 📈 حداکثر: {svc['max']}\n\n"
            "🔗 لینک صفحه را بفرستید:",
            parse_mode="HTML"
        )
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)


@router.message(USMMState.order_link)
async def usmm_order_link(msg: Message, state: FSMContext):
    link = (msg.text or "").strip()
    if not link.startswith("http"):
        await msg.answer("❌ لینک معتبر وارد کنید (http...)")
        return
    data = await state.get_data()
    svc  = data["svc"]
    await state.update_data(link=link)
    await state.set_state(USMMState.order_qty)
    await msg.answer(
        f"✅ لینک ثبت شد.\n\n"
        f"🔢 تعداد را وارد کنید:\n"
        f"📉 حداقل: <b>{svc['min']}</b> | 📈 حداکثر: <b>{svc['max']}</b>",
        parse_mode="HTML"
    )


@router.message(USMMState.order_qty)
async def usmm_order_qty(msg: Message, state: FSMContext, db_user: User = None):
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return

    data = await state.get_data()
    svc  = data["svc"]
    link = data["link"]

    if qty < int(svc["min"]) or qty > int(svc["max"]):
        await msg.answer(
            f"❌ تعداد باید بین <b>{svc['min']}</b> و <b>{svc['max']}</b> باشد.",
            parse_mode="HTML"
        )
        return

    await state.clear()

    async with AsyncSessionLocal() as session:
        user = await get_user(session, msg.from_user.id)
        if not user:
            await msg.answer("❌ خطای داخلی.")
            return

        prices = await calc_order_price(session, float(svc["rate"]), qty)
        sell   = prices["sell"]
        bal    = float(user.balance or 0)

        if bal < sell:
            await msg.answer(
                f"❌ <b>موجودی کافی ندارید.</b>\n"
                f"💰 هزینه: <b>${sell:.4f}</b> | موجودی: <b>${bal:.2f}</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ شارژ حساب", callback_data="user_deposit")],
                    [InlineKeyboardButton(text="🏠 منو", callback_data="user_home")],
                ]),
                parse_mode="HTML"
            )
            return

        # Place order on SMMPass
        try:
            from services.smmpass import add_order_default
            result = await add_order_default(svc["service"], link, qty)
            smm_id = result.get("order", "?")
        except Exception as e:
            await msg.answer(f"❌ خطا در ارسال سفارش: <code>{str(e)[:100]}</code>", parse_mode="HTML")
            return

        order = await create_order(
            session, user.id,
            svc["service"], svc["name"],
            link, qty,
            cost_price=prices["cost"],
            sell_price=sell,
        )
        if not order:
            await msg.answer("❌ موجودی کافی ندارید.")
            return

    await msg.answer(
        f"✅ <b>سفارش ثبت شد!</b>\n\n"
        f"📦 شناسه: <code>{order.id}</code>\n"
        f"🔢 SMM ID: <code>{smm_id}</code>\n"
        f"💰 هزینه: <b>${sell:.4f}</b>\n"
        f"💰 موجودی باقیمانده: <b>${bal - sell:.2f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 سفارش‌های من", callback_data="user_orders")],
            [InlineKeyboardButton(text="🏠 منو", callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "usmm_search")
async def usmm_search_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(USMMState.search)
    await cb.message.edit_text(
        "🔍 <b>جستجو در خدمات</b>\n\n"
        "نام سرویس یا دسته را بنویسید:\n"
        "<i>مثال: instagram followers</i>",
        parse_mode="HTML"
    )


@router.message(USMMState.search)
async def usmm_search_handle(msg: Message, state: FSMContext):
    q = (msg.text or "").strip().lower()
    await state.clear()
    try:
        from services.smmpass import get_services
        svcs    = await get_services()
        results = [s for s in svcs
                   if q in s["name"].lower() or q in s["category"].lower()
                   or q == str(s["service"])]

        if not results:
            await msg.answer(
                f"❌ نتیجه‌ای برای '<b>{q}</b>' یافت نشد.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")]
                ]),
                parse_mode="HTML"
            )
            return

        async with AsyncSessionLocal() as session:
            markup_pct = await get_markup(session)

        rows = []
        for s in results[:20]:
            user_rate = apply_markup(float(s["rate"]), markup_pct)
            name = s['name'][:24] + "…" if len(s['name']) > 24 else s['name']
            rows.append([InlineKeyboardButton(
                text=f"[{s['service']}] {name} | ${user_rate:.4f}",
                callback_data=f"usmm_svc_{s['service']}"
            )])
        rows.append([InlineKeyboardButton(text="🏠 بازگشت", callback_data="user_home")])

        suffix = " (اول 20)" if len(results) > 20 else ""
        await msg.answer(
            f"🔍 '<b>{q}</b>': <b>{len(results)}</b> سرویس{suffix}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.answer(f"❌ <code>{str(e)[:200]}</code>", parse_mode="HTML")
