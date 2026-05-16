"""
FJPanel SMM Panel Handler
API: https://fjpanel.com/api/v2
Features: balance, service browser, order, order status
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

FJ_URL = "https://fjpanel.com/api/v2"
FJ_KEY = os.getenv("FJPANEL_KEY", "656AEGDB99092971778949517YVWUZ734LMKIH9909STPRQ774")

# Category icons
CAT_ICONS = {
    "اینستاگرام": "📸",
    "فالوور": "👥",
    "لایک": "❤️",
    "کامنت": "💬",
    "استوری": "📍",
    "ریلز": "🎬",
    "ویو": "👁",
    "بازدید": "👁",
    "تلگرام": "📢",
    "یوتیوب": "🎥",
    "تیک تاک": "🎵",
    "روبیکا": "🟥",
    "روبینو": "🟥",
    "ایتا": "🟦",
    "لایو": "🟡",
    "تردز": "⚫",
    "کلاب": "🎤",
    "یوتیوب": "🎥",
}

def _cat_icon(cat: str) -> str:
    for k, v in CAT_ICONS.items():
        if k in cat:
            return v
    return "📦"


# ─── FSM ──────────────────────────────────────────────────────────────────────
class FJState(StatesGroup):
    order_link     = State()
    order_qty      = State()
    order_confirm  = State()
    check_order_id = State()


# ─── API ────────────────────────────────────────────────────────────────────────────────
async def fj_request(data: dict) -> dict:
    import httpx
    data["key"] = FJ_KEY
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(FJ_URL, data=data)
        return r.json()


async def get_services() -> dict:
    """Returns {category: [service, ...]} excluding test/disabled."""
    data = await fj_request({"action": "services"})
    cats = {}
    for s in data:
        cat = str(s.get("category", "Other"))
        if "تست" in cat:
            continue
        rate = float(str(s.get("rate", 0)))
        if rate >= 1e17:  # disabled
            continue
        if cat not in cats:
            cats[cat] = []
        cats[cat].append(s)
    return cats


async def get_balance() -> tuple[str, str]:
    data = await fj_request({"action": "balance"})
    return str(data.get("balance", "?")).replace("0", "0"), str(data.get("currency", "Rial"))


async def add_order(service_id: int, link: str, quantity: int) -> dict:
    return await fj_request({
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity,
    })


async def get_order_status(order_id: int) -> dict:
    return await fj_request({"action": "status", "order": order_id})


# ─── Keyboards ─────────────────────────────────────────────────────────────────────────────
def fj_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 موجودی حساب",      callback_data="fj_balance")],
        [InlineKeyboardButton(text="📊 لیست خدمات",       callback_data="fj_services")],
        [InlineKeyboardButton(text="➕ ثبت سفارش جدید",   callback_data="fj_new_order")],
        [InlineKeyboardButton(text="🔍 وضعیت سفارش",     callback_data="fj_check_order")],
        [InlineKeyboardButton(text="🔙 بازگشت",           callback_data="menu_main")],
    ])


# ─── Main menu ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_fjpanel")
async def menu_fjpanel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "🛠 <b>FJPanel — پنل خدمات شبکه‌های اجتماعی</b>\n\n"
        "یک گزینه را انتخاب کنید:",
        reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Balance ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_balance")
async def fj_balance(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("⏳ در حال دریافت...", parse_mode="HTML")
    try:
        bal, cur = await get_balance()
        text = (
            f"💰 <b>موجودی حساب FJPanel</b>\n\n"
            f"💵 موجودی: <b>{bal}</b> {cur}"
        )
    except Exception as e:
        text = f"❌ خطا: {e}"
    await cb.message.edit_text(text, reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Services browser ───────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_services")
async def fj_services(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_text("⏳ در حال دریافت خدمات...", parse_mode="HTML")
    try:
        cats = await get_services()
    except Exception as e:
        await cb.message.edit_text(f"❌ {e}", reply_markup=fj_main_menu(), parse_mode="HTML")
        return

    await state.update_data(fj_cats={
        k: [{"id": s["service"], "name": s["name"],
             "rate": s["rate"], "min": s["min"], "max": s["max"],
             "type": s.get("type","Default")}
            for s in v]
        for k, v in cats.items()
    })

    rows = []
    for cat in cats:
        icon = _cat_icon(cat)
        rows.append([InlineKeyboardButton(
            text=f"{icon} {cat} ({len(cats[cat])})",
            callback_data=f"fj_cat:{cat[:40]}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_fjpanel")])

    await cb.message.edit_text(
        f"📊 <b>دسته‌بندی خدمات</b> ({sum(len(v) for v in cats.values())} خدمت)\n"
        f"یک دسته را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_cat:"))
async def fj_cat(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    cat = cb.data[7:]
    data = await state.get_data()
    cats = data.get("fj_cats", {})

    # Find matching category
    matched_cat = None
    for k in cats:
        if k[:40] == cat:
            matched_cat = k
            break
    if not matched_cat:
        await cb.answer("دسته پیدا نشد.", show_alert=True); return

    services = cats[matched_cat]
    icon = _cat_icon(matched_cat)
    lines = [f"{icon} <b>{matched_cat}</b>\n"]
    rows  = []

    for s in services:
        rate_fmt = f"{float(s['rate']):,.0f}"
        lines.append(
            f"🔹 <b>{s['name']}</b>\n"
            f"   🔑 ID: <code>{s['id']}</code> | 💰 {rate_fmt} ریال/هزار\n"
            f"   📊 حداقل: {s['min']} | حداکثر: {s['max']}"
        )
        rows.append([InlineKeyboardButton(
            text=f"➕ سفارش — {s['name'][:35]}",
            callback_data=f"fj_order:{s['id']}"
        )])

    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="fj_services")])

    # Split if too long
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n..."

    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML")


# ─── New order flow ───────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_new_order")
async def fj_new_order(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(FJState.order_link)
    await state.update_data(fj_service_id=None)
    await cb.message.edit_text(
        "➕ <b>سفارش جدید</b>\n\n"
        "ابتدا <b>ID خدمت</b> را بفرستید:\n"
        "<i>(مثال: 473)</i>\n\n"
        "💡 از بخش لیست خدمات ID را پیدا کنید.",
        parse_mode="HTML")


@router.callback_query(F.data.startswith("fj_order:"))
async def fj_order_from_list(cb: CallbackQuery, state: FSMContext):
    """Start order from service list button."""
    await cb.answer()
    service_id = int(cb.data.split(":")[1])
    await state.set_state(FJState.order_link)
    await state.update_data(fj_service_id=service_id)
    await cb.message.edit_text(
        f"➕ <b>سفارش خدمت #{service_id}</b>\n\n"
        f"لینک صفحه را بفرستید:\n"
        f"<i>(مثال: https://instagram.com/username)</i>",
        parse_mode="HTML")


@router.message(FJState.order_link)
async def fj_order_link(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    text = (msg.text or "").strip()

    data = await state.get_data()
    service_id = data.get("fj_service_id")

    # If no service_id yet, this message is the service ID
    if service_id is None:
        try:
            service_id = int(text)
            await state.update_data(fj_service_id=service_id)
            await msg.answer(
                f"🔑 خدمت <code>{service_id}</code> انتخاب شد.\n\n"
                f"الان لینک صفحه را بفرستید:",
                parse_mode="HTML")
            return
        except ValueError:
            await msg.answer("❌ ID خدمت باید عدد باشد.")
            return

    # This is the link
    await state.update_data(fj_link=text)
    await state.set_state(FJState.order_qty)
    await msg.answer(
        f"🔗 لینک: <code>{text[:60]}</code>\n\n"
        f"حالا <b>تعداد</b> را وارد کنید:",
        parse_mode="HTML")


@router.message(FJState.order_qty)
async def fj_order_qty(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        qty = int((msg.text or "").strip())
        if qty < 1: raise ValueError
    except ValueError:
        await msg.answer("❌ تعداد باید عدد باشد."); return

    data = await state.get_data()
    await state.update_data(fj_qty=qty)
    await state.set_state(FJState.order_confirm)

    service_id = data["fj_service_id"]
    link       = data["fj_link"]

    await msg.answer(
        f"✅ <b>تایید سفارش</b>\n\n"
        f"🔑 خدمت: <code>{service_id}</code>\n"
        f"🔗 لینک: <code>{link[:60]}</code>\n"
        f"📊 تعداد: <b>{qty:,}</b>\n\n"
        f"آیا اطمینان دارید؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ثبت سفارش", callback_data="fj_confirm_yes")],
            [InlineKeyboardButton(text="❌ لغو",          callback_data="menu_fjpanel")],
        ]),
        parse_mode="HTML")


@router.callback_query(F.data == "fj_confirm_yes")
async def fj_confirm_yes(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    service_id = data.get("fj_service_id")
    link       = data.get("fj_link")
    qty        = data.get("fj_qty")
    await state.clear()

    await cb.message.edit_text("⏳ در حال ثبت سفارش...", parse_mode="HTML")
    try:
        result = await add_order(service_id, link, qty)
        if "order" in result:
            order_id = result["order"]
            text = (
                f"✅ <b>سفارش ثبت شد!</b>\n\n"
                f"📝 شماره سفارش: <code>{order_id}</code>\n"
                f"🔑 خدمت: <code>{service_id}</code>\n"
                f"📊 تعداد: <b>{qty:,}</b>\n\n"
                f"💡 برای بررسی وضعیت از بخش وضعیت سفارش استفاده کنید."
            )
        elif "error" in result:
            text = f"❌ خطا: {result['error']}"
        else:
            text = f"❌ پاسخ نامشخص: {result}"
    except Exception as e:
        text = f"❌ خطا: {e}"

    await cb.message.edit_text(text, reply_markup=fj_main_menu(), parse_mode="HTML")


# ─── Order status ───────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "fj_check_order")
async def fj_check_order(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(FJState.check_order_id)
    await cb.message.edit_text(
        "🔍 <b>وضعیت سفارش</b>\n\n"
        "شماره سفارش را وارد کنید:",
        parse_mode="HTML")


@router.message(FJState.check_order_id)
async def fj_check_order_id(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        order_id = int((msg.text or "").strip())
    except ValueError:
        await msg.answer("❌ شماره سفارش باید عدد باشد."); return
    await state.clear()

    wait = await msg.answer("⏳ در حال بررسی...", parse_mode="HTML")
    try:
        result = await get_order_status(order_id)
        status  = result.get("status", "?")
        charge  = result.get("charge", "?")
        cur     = result.get("currency", "Rial")
        remains = result.get("remains", "")
        start   = result.get("start_count", "")

        STATUS_ICONS = {
            "Pending":    "⏳",
            "In progress": "⚡",
            "Completed":  "✅",
            "Partial":    "⚠️",
            "Canceled":   "❌",
            "Processing": "🔄",
        }
        icon = STATUS_ICONS.get(status, "🟡")

        lines = [
            f"🔍 <b>وضعیت سفارش #{order_id}</b>\n",
            f"{icon} وضعیت: <b>{status}</b>",
            f"💰 هزینه: <b>{charge}</b> {cur}",
        ]
        if remains: lines.append(f"📊 باقیمانده: <b>{remains}</b>")
        if start:   lines.append(f"📈 شروع: <b>{start}</b>")

        text = "\n".join(lines)
    except Exception as e:
        text = f"❌ خطا: {e}"

    await wait.edit_text(text, reply_markup=fj_main_menu(), parse_mode="HTML")
