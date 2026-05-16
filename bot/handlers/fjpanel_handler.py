"""
FJPanel SMM Panel handler.
Features:
- موجودی حساب
- لیست سرویس‌ها با جستجو و فیلتر دسته‌بندی
- ثبت سفارش جدید
- وضعیت سفارش
- تاریخچه سفارش‌ها
"""
import asyncio
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

PAGE_SIZE = 8   # services per page


# ─── FSM ──────────────────────────────────────────────────────────────────────
class FJState(StatesGroup):
    search_query   = State()   # search in service list
    order_link     = State()   # waiting for link
    order_quantity = State()   # waiting for quantity
    order_status   = State()   # waiting for order ID


# ─── Cache ──────────────────────────────────────────────────────────────────────
_services_cache: list = []
_cache_time: float = 0
CACHE_TTL = 300  # 5 min


async def _get_services_cached() -> list:
    import time
    global _services_cache, _cache_time
    if _services_cache and (time.time() - _cache_time) < CACHE_TTL:
        return _services_cache
    from services.fjpanel import get_services
    _services_cache = await get_services()
    _cache_time = time.time()
    return _services_cache


# ─── Keyboards ────────────────────────────────────────────────────────────────────
def fj_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 موجودی حساب",         callback_data="fj_balance")],
        [InlineKeyboardButton(text="📋 لیست سرویس‌ها",        callback_data="fj_services_0")],
        [InlineKeyboardButton(text="🔍 جستجو در سرویس‌ها",   callback_data="fj_search")],
        [InlineKeyboardButton(text="➕ ثبت سفارش جدید",      callback_data="fj_new_order")],
        [InlineKeyboardButton(text="📦 وضعیت سفارش",         callback_data="fj_order_status")],
        [InlineKeyboardButton(text="🔙 بازگشت",               callback_data="menu_main")],
    ])


def _services_keyboard(services: list, page: int, category: str = ""):
    """Build paginated service list keyboard."""
    filtered = [s for s in services
                if not category or s.get("category", "") == category]
    total   = len(filtered)
    start   = page * PAGE_SIZE
    end     = start + PAGE_SIZE
    chunk   = filtered[start:end]

    rows = []
    for s in chunk:
        label = f"🔹 [{s['service']}] {s['name'][:28]} | 💰{s['rate']} ریال"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"fj_svc_{s['service']}"
        )])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ قبل", callback_data=f"fj_services_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{(total-1)//PAGE_SIZE+1}", callback_data="fj_noop"))
    if end < total:
        nav.append(InlineKeyboardButton(text="بعد ➡️", callback_data=f"fj_services_{page+1}"))
    if nav: rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="fj_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Handlers ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_fjpanel")
async def fj_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🛠 <b>FJPanel — پنل SMM</b>\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=fj_main_menu(), parse_mode="HTML")

@router.callback_query(F.data == "fj_menu")
async def fj_menu_back(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🛠 <b>FJPanel — پنل SMM</b>\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=fj_main_menu(), parse_mode="HTML")

@router.callback_query(F.data == "fj_noop")
async def fj_noop(cb: CallbackQuery):
    await cb.answer()


# ─── Balance ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_balance")
async def fj_balance(cb: CallbackQuery):
    await cb.answer()
    msg = await cb.message.edit_text("⏳ در حال دریافت موجودی...", parse_mode="HTML")
    try:
        from services.fjpanel import get_balance
        data = await get_balance()
        balance  = data.get("balance", "?")  
        currency = data.get("currency", "Rial")
        text = (
            f"💰 <b>موجودی حساب FJPanel</b>\n\n"
            f"💵 موجودی: <b>{float(balance):,.2f}</b> {currency}"
        )
    except Exception as e:
        text = f"❌ خطا: {str(e)[:80]}"
    await msg.edit_text(text, reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Services list ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("fj_services_"))
async def fj_services(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    msg  = await cb.message.edit_text("⏳ در حال دریافت سرویس‌ها...", parse_mode="HTML")
    try:
        services = await _get_services_cached()
        if not services:
            await msg.edit_text("❌ سرویسی یافت نشد.",
                                reply_markup=fj_main_menu(), parse_mode="HTML")
            return

        # Get unique categories
        cats = list(dict.fromkeys(s.get("category","") for s in services))
        total = len(services)

        # Check if filtering by category stored in state
        data = await state.get_data()
        cat_filter = data.get("fj_cat", "")
        filtered = [s for s in services
                    if not cat_filter or s.get("category") == cat_filter]

        kb = _services_keyboard(services if not cat_filter else filtered, page, cat_filter)

        # Category filter buttons
        cat_rows = []
        for i in range(0, len(cats), 2):
            row = []
            for cat in cats[i:i+2]:
                short = cat[:20]
                active = "✅ " if cat == cat_filter else ""
                row.append(InlineKeyboardButton(
                    text=f"{active}{short}",
                    callback_data=f"fj_cat_{cat[:30]}"
                ))
            cat_rows.append(row)
        if cat_filter:
            cat_rows.append([InlineKeyboardButton(
                text="❌ حذف فیلتر", callback_data="fj_cat_clear")])

        # Merge category rows into keyboard
        all_rows = cat_rows + kb.inline_keyboard
        kb = InlineKeyboardMarkup(inline_keyboard=all_rows)

        header = f"📌 دسته: <b>{cat_filter}</b>\n" if cat_filter else ""
        await msg.edit_text(
            f"📊 <b>سرویس‌ها ({len(filtered)} مورد)</b>\n"
            f"{header}"
            f"روی هر سرویس بزنید تا جزئیات ببینید:",
            reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await msg.edit_text(f"❌ خطا: {str(e)[:80]}",
                            reply_markup=fj_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_cat_"))
async def fj_cat_filter(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cat = cb.data[7:]  # remove "fj_cat_"
    if cat == "clear":
        await state.update_data(fj_cat="")
    else:
        await state.update_data(fj_cat=cat)
    # Rebuild services page 0
    cb.data = "fj_services_0"
    await fj_services(cb, state)


@router.callback_query(F.data.startswith("fj_svc_"))
async def fj_service_detail(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        services = await _get_services_cached()
        svc = next((s for s in services if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("❌ سرویس یافت نشد.", show_alert=True)
            return

        text = (
            f"🔹 <b>{svc['name']}</b>\n\n"
            f"🏷 دسته: <code>{svc.get('category','?')}</code>\n"
            f"🔢 شناسه: <code>{svc['service']}</code>\n"
            f"💰 نرخ: <b>{svc['rate']}</b> ریال به ازای 1000\n"
            f"📉 حداقل: <b>{svc['min']}</b>\n"
            f"📈 حداکثر: <b>{svc['max']}</b>\n"
            f"📌 نوع: <code>{svc.get('type','?')}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"➕ ثبت سفارش با سرویس {svc_id}",
                callback_data=f"fj_order_svc_{svc_id}"
            )],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="fj_services_0")],
        ])
        await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)


# ─── Search ──────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_search")
async def fj_search_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(FJState.search_query)
    await cb.message.edit_text(
        "🔍 <b>جستجو در سرویس‌ها</b>\n\n"
        "نام سرویس یا دسته را بنویسید:\n"
        "<i>مثال: followers, instagram, like</i>",
        parse_mode="HTML")

@router.message(FJState.search_query)
async def fj_search_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    query = (msg.text or "").strip().lower()
    await state.clear()

    try:
        services = await _get_services_cached()
        results  = [
            s for s in services
            if query in s.get("name","").lower()
            or query in s.get("category","").lower()
            or query in str(s.get("service",""))
        ]

        if not results:
            await msg.answer(
                f"❌ نتیجه‌ای برای '<b>{query}</b>' یافت نشد.",
                reply_markup=fj_main_menu(), parse_mode="HTML")
            return

        rows = []
        for s in results[:20]:
            rows.append([InlineKeyboardButton(
                text=f"🔹 [{s['service']}] {s['name'][:28]} | {s['rate']} ریال",
                callback_data=f"fj_svc_{s['service']}"
            )])
        rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="fj_menu")])

        await msg.answer(
            f"🔍 نتایج جستجو '<b>{query}</b>': <b>{len(results)}</b> مورد"
            + (f" (10 اول نمایش داده شد)" if len(results) > 20 else ""),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"❌ خطا: {str(e)[:80]}", reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── New Order ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_new_order")
async def fj_new_order(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(FJState.search_query)
    await state.update_data(fj_order_mode=True)
    await cb.message.edit_text(
        "➕ <b>ثبت سفارش جدید</b>\n\n"
        "ابتدا نام سرویس یا شناسه سرویس را بنویسید:\n"
        "<i>مثال: followers یا 110</i>",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_order_svc_"))
async def fj_order_svc(cb: CallbackQuery, state: FSMContext):
    """Start order flow for a specific service."""
    await cb.answer()
    svc_id = int(cb.data.split("_")[-1])
    try:
        services = await _get_services_cached()
        svc = next((s for s in services if s["service"] == svc_id), None)
        if not svc:
            await cb.answer("❌ سرویس یافت نشد.", show_alert=True); return

        await state.update_data(fj_svc_id=svc_id, fj_svc=svc)
        await state.set_state(FJState.order_link)
        await cb.message.edit_text(
            f"➕ <b>سفارش سرویس [{svc_id}] {svc['name']}</b>\n\n"
            f"💰 نرخ: {svc['rate']} ریال / 1000\n"
            f"📉 حداقل: {svc['min']} | 📈 حداکثر: {svc['max']}\n\n"
            f"🔗 لینک صفحه را بفرستید:",
            parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)


@router.message(FJState.order_link)
async def fj_order_link(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    link = (msg.text or "").strip()
    if not link.startswith("http"):
        await msg.answer("❌ لینک معتبر وارد کنید."); return

    data = await state.get_data()
    svc  = data.get("fj_svc", {})
    await state.update_data(fj_link=link)
    await state.set_state(FJState.order_quantity)
    await msg.answer(
        f"🔢 تعداد مورد نیاز را وارد کنید:\n"
        f"📉 حداقل: <b>{svc.get('min','?')}</b> | "
        f"📈 حداکثر: <b>{svc.get('max','?')}</b>",
        parse_mode="HTML")


@router.message(FJState.order_quantity)
async def fj_order_quantity(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید."); return

    data   = await state.get_data()
    svc_id = data["fj_svc_id"]
    svc    = data["fj_svc"]
    link   = data["fj_link"]
    await state.clear()

    # Validate range
    mn = int(svc.get("min", 0))
    mx = int(svc.get("max", 999999))
    if qty < mn or qty > mx:
        await msg.answer(
            f"❌ تعداد باید بین <b>{mn}</b> و <b>{mx}</b> باشد.",
            parse_mode="HTML"); return

    # Cost estimate
    rate = float(svc.get("rate", 0))
    cost = (rate * qty) / 1000

    status_msg = await msg.answer(
        f"⏳ در حال ثبت سفارش...\n"
        f"🔹 سرویس: [{svc_id}] {svc['name']}\n"
        f"🔗 لینک: <code>{link[:50]}</code>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        f"💰 هزینه تخمینی: <b>{cost:,.2f}</b> ریال",
        parse_mode="HTML")

    try:
        from services.fjpanel import add_order
        result = await add_order(svc_id, link, qty)
        order_id = result.get("order")
        if order_id:
            await status_msg.edit_text(
                f"✅ <b>سفارش ثبت شد!</b>\n\n"
                f"📦 شناسه سفارش: <code>{order_id}</code>\n"
                f"🔹 سرویس: {svc['name']}\n"
                f"🔢 تعداد: {qty:,}\n"
                f"💰 هزینه تخمینی: {cost:,.2f} ریال\n\n"
                f"ℹ️ برای وضعیت سفارش از بخش 'وضعیت سفارش' استفاده کنید.",
                reply_markup=fj_main_menu(), parse_mode="HTML")
        else:
            raise ValueError(str(result))
    except Exception as e:
        await status_msg.edit_text(
            f"❌ خطا در ثبت سفارش:\n<code>{str(e)[:100]}</code>",
            reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Order Status ───────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_order_status")
async def fj_order_status_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(FJState.order_status)
    await cb.message.edit_text(
        "📦 <b>وضعیت سفارش</b>\n\n"
        "شناسه سفارش را وارد کنید:",
        parse_mode="HTML")


@router.message(FJState.order_status)
async def fj_order_status_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        order_id = int((msg.text or "").strip())
    except ValueError:
        await msg.answer("❌ شناسه سفارش باید عدد باشد."); return
    await state.clear()

    status_msg = await msg.answer("⏳ در حال دریافت وضعیت...", parse_mode="HTML")
    try:
        from services.fjpanel import get_order_status
        data = await get_order_status(order_id)

        status   = data.get("status", "?")
        charge   = data.get("charge", "?")
        currency = data.get("currency", "Rial")

        # Status emoji
        status_lower = status.lower()
        if "complet" in status_lower or "done" in status_lower:
            icon = "✅"
        elif "pending" in status_lower or "process" in status_lower:
            icon = "⏳"
        elif "cancel" in status_lower or "fail" in status_lower:
            icon = "❌"
        elif "partial" in status_lower:
            icon = "⚠️"
        else:
            icon = "🟡"

        await status_msg.edit_text(
            f"📦 <b>وضعیت سفارش #{order_id}</b>\n\n"
            f"{icon} وضعیت: <b>{status}</b>\n"
            f"💰 هزینه: <b>{charge}</b> {currency}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 به‌روزرسانی",
                                     callback_data=f"fj_refresh_{order_id}")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="fj_menu")],
            ]),
            parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(
            f"❌ خطا: {str(e)[:80]}",
            reply_markup=fj_main_menu(), parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_refresh_"))
async def fj_refresh_order(cb: CallbackQuery):
    await cb.answer("🔄 در حال به‌روزرسانی...")
    order_id = int(cb.data.split("_")[-1])
    try:
        from services.fjpanel import get_order_status
        data = await get_order_status(order_id)
        status   = data.get("status", "?")
        charge   = data.get("charge", "?")
        currency = data.get("currency", "Rial")
        status_lower = status.lower()
        if "complet" in status_lower or "done" in status_lower: icon = "✅"
        elif "pending" in status_lower or "process" in status_lower: icon = "⏳"
        elif "cancel" in status_lower or "fail" in status_lower: icon = "❌"
        elif "partial" in status_lower: icon = "⚠️"
        else: icon = "🟡"

        await cb.message.edit_text(
            f"📦 <b>وضعیت سفارش #{order_id}</b>\n\n"
            f"{icon} وضعیت: <b>{status}</b>\n"
            f"💰 هزینه: <b>{charge}</b> {currency}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 به‌روزرسانی",
                                     callback_data=f"fj_refresh_{order_id}")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="fj_menu")],
            ]),
            parse_mode="HTML")
    except Exception as e:
        await cb.answer(f"❌ {str(e)[:60]}", show_alert=True)
