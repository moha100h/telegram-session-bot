"""
SMMPass user panel — professional, fully working.
Prices shown to users are RAW API prices (no markup).
"""
import hashlib, logging, math
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from db.models import User
from services.smmpass import (
    get_services, add_order_default, add_order_package,
    add_order_mentions_hashtag, add_order_mentions_custom,
    add_order_custom_comments, add_order_subscription,
    get_order_status, get_categories,
)
from services.user_service import deduct_balance, add_balance
from services.order_service import create_order
from services.settings_service import get_setting
from services.order_service import calc_order_price

logger   = logging.getLogger("smm_user")
router   = Router()
PAGE_CAT = 5
PAGE_SVC = 6
_cat_map: dict = {}

def _ch(cat: str) -> str:
    h = hashlib.md5(cat.encode()).hexdigest()[:8]
    _cat_map[h] = cat
    return h

def _cn(h: str) -> str:
    return _cat_map.get(h, "")

class SPState(StatesGroup):
    order_link   = State()
    order_qty    = State()
    order_extra  = State()
    sub_username = State()
    sub_min      = State()
    sub_max      = State()
    check_status = State()

STATUS_ICONS = {
    "pending": "⏳", "processing": "🔄", "in progress": "🔄",
    "completed": "✅", "partial": "⚠️", "cancelled": "❌",
    "failed": "💔", "refunded": "↩️",
}
TYPE_LABELS = {
    "default": "پیش‌فرض", "package": "پکیج",
    "custom_comments": "کامنت دلخواه", "mentions_hashtag": "منشن هشتگ",
    "mentions_custom": "منشن دلخواه", "mentions_hashtags": "منشن هشتگ",
    "mentions_followers": "منشن فالوور", "comment_likes": "لایک کامنت",
    "subscription": "اشتراک", "poll": "نظرسنجی",
}
CAT_ICONS = {
    "member": "👥", "view": "👁", "reaction": "👍", "share": "📤",
    "story": "📸", "bot": "🤖", "activity": "🧠", "ads": "📣",
    "growth": "📈", "vote": "🗳", "free": "🎁", "spotify": "🎵",
    "comment": "💬", "like": "❤️", "follow": "➕", "sub": "🔔",
}

def _cicon(cat: str) -> str:
    c = cat.lower()
    for k, v in CAT_ICONS.items():
        if k in c:
            return v
    return "📌"

def _total(rate: float, qty: int, markup: float = 0.0) -> float:
    base = rate * qty / 1000
    return round(base * (1 + markup / 100), 4)


# ── Entry ─────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_smmpass")
async def sp_entry(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await state.clear()
    await cb.answer()
    async with AsyncSessionLocal() as session:
        btn_name = await get_setting(session, "smm_panel_title", "🚀 پنل SMM")
    services = await get_services()
    bal  = float(db_user.balance or 0) if db_user else 0
    cats = get_categories(services)
    await cb.message.edit_text(
        f"<b>{btn_name}</b>\n\n"
        f"💰 موجودی: <b>${bal:.2f}</b>\n"
        f"📊 سرویس‌های فعال: <b>{len(services)}</b> در <b>{len(cats)}</b> دسته\n\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش جدید",   callback_data="sp_cats_0")],
            [InlineKeyboardButton(text="📦 سفارشات من",    callback_data="sp_my_orders")],
            [InlineKeyboardButton(text="🔍 وضعیت سفارش",  callback_data="sp_check_status")],
            [InlineKeyboardButton(text="💳 شارژ موجودی",   callback_data="user_deposit")],
            [InlineKeyboardButton(text="🏠 خانه",           callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


# ── Categories ────────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("sp_cats_"))
async def sp_cats(cb: CallbackQuery):
    await cb.answer()
    page     = int(cb.data.split("_")[-1])
    services = await get_services()
    cats     = get_categories(services)
    cat_list = list(cats.items())
    total    = max(1, math.ceil(len(cat_list) / PAGE_CAT))
    page     = max(0, min(page, total - 1))
    buttons  = []
    for cat, svcs in cat_list[page * PAGE_CAT:(page + 1) * PAGE_CAT]:
        icon  = _cicon(cat)
        short = cat.replace("TG - ", "").replace("Telegram - ", "")[:30]
        min_r = min(float(s.get("rate", 0)) for s in svcs)
        h     = _ch(cat)
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {short}  ({len(svcs)})",
            callback_data=f"sp_cat_{h}_0"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"sp_cats_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{total}", callback_data="sp_noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"sp_cats_{page+1}"))
    buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_smmpass")])
    await cb.message.edit_text(
        f"📋 <b>دسته‌بندی‌ها</b> — صفحه {page+1}/{total}\n\nیک دسته را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "sp_noop")
async def sp_noop(cb: CallbackQuery):
    await cb.answer()


# ── Services in category ──────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("sp_cat_"))
async def sp_cat_svcs(cb: CallbackQuery):
    await cb.answer()
    parts    = cb.data.split("_")
    cat_hash = parts[2]
    page     = int(parts[3])
    cat      = _cn(cat_hash)
    if not cat:
        await cb.answer("دسته یافت نشد!", show_alert=True); return
    services = await get_services()
    cat_svcs = [s for s in services if s.get("category") == cat]
    total    = max(1, math.ceil(len(cat_svcs) / PAGE_SVC))
    page     = max(0, min(page, total - 1))
    buttons  = []
    async with AsyncSessionLocal() as _s2:
        from services.settings_service import get_setting as _gs2
        _markup = float(await _gs2(_s2, "smm_markup_percent", "0"))
    for s in cat_svcs[page * PAGE_SVC:(page + 1) * PAGE_SVC]:
        rate      = float(s.get("rate", 0))
        sell_rate = round(rate * (1 + _markup / 100), 4)
        buttons.append([InlineKeyboardButton(
            text=f"{s['name'][:35]}  ·  ${sell_rate:.4f}/1K",
            callback_data=f"sp_svc_{s['service']}"
        )])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"sp_cat_{cat_hash}_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{total}", callback_data="sp_noop"))
    if page < total - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"sp_cat_{cat_hash}_{page+1}"))
    buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="sp_cats_0")])
    short = cat.replace("TG - ", "").replace("Telegram - ", "")[:35]
    await cb.message.edit_text(
        f"📌 <b>{short}</b>\nصفحه {page+1}/{total} · {len(cat_svcs)} سرویس\n\nیک سرویس انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


# ── Service detail ────────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("sp_svc_"))
async def sp_svc_detail(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await cb.answer()
    svc_id   = cb.data[7:]
    services = await get_services()
    svc      = next((s for s in services if str(s["service"]) == str(svc_id)), None)
    if not svc:
        await cb.answer("سرویس یافت نشد!", show_alert=True); return
    rate     = float(svc.get("rate", 0))
    min_q    = int(svc.get("min", 1))
    max_q    = int(svc.get("max", 1000000))
    svc_type = svc.get("type", "default")
    desc     = (svc.get("desc") or "")[:300]
    bal      = float(db_user.balance or 0) if db_user else 0
    async with AsyncSessionLocal() as _s:
        from services.settings_service import get_setting as _gs
        markup = float(await _gs(_s, "smm_markup_percent", "0"))
    sell_rate = round(rate * (1 + markup / 100), 4)
    await state.update_data(
        sp_svc_id=str(svc_id), sp_svc_name=svc["name"],
        sp_rate=rate, sp_sell_rate=sell_rate, sp_markup=markup,
        sp_min=min_q, sp_max=max_q, sp_type=svc_type,
    )
    text = (
        f"🛒 <b>{svc['name']}</b>\n\n"
        f"💰 قیمت: <b>${sell_rate:.4f}</b> / هر ۱۰۰۰\n"
        f"📊 حداقل: <b>{min_q:,}</b>  |  حداکثر: <b>{max_q:,}</b>\n"
        f"🔧 نوع: <b>{TYPE_LABELS.get(svc_type, svc_type)}</b>\n"
        f"💳 موجودی شما: <b>${bal:.2f}</b>\n"
    )
    if desc:
        text += f"\n📝 <i>{desc}</i>\n"
    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ثبت سفارش", callback_data="sp_start_order")],
            [InlineKeyboardButton(text="🔙 بازگشت",    callback_data="sp_cats_0")],
        ]),
        parse_mode="HTML"
    )


# ── Order flow ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_start_order")
async def sp_start_order(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data     = await state.get_data()
    svc_type = data.get("sp_type", "default")
    if svc_type == "subscription":
        await state.set_state(SPState.sub_username)
        await cb.message.edit_text(
            "📌 <b>اشتراک</b>\n\nیوزرنیم کانال یا گروه را وارد کنید (بدون @):\n\n/cancel برای لغو",
            parse_mode="HTML"
        )
        return
    await state.set_state(SPState.order_link)
    hints = {
        "package": "لینک کانال یا پست", "poll": "لینک پست نظرسنجی",
        "mentions_hashtag": "لینک پست تلگرام", "mentions_custom": "لینک پست تلگرام",
        "custom_comments": "لینک پست تلگرام", "comment_likes": "لینک کامنت",
    }
    await cb.message.edit_text(
        f"🔗 <b>لینک را وارد کنید:</b>\n<i>{hints.get(svc_type, 'لینک پست یا کانال تلگرام')}</i>\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(SPState.order_link)
async def sp_got_link(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    link = (msg.text or "").strip()
    if not link:
        await msg.answer("❌ لینک معتبر وارد کنید."); return
    await state.update_data(sp_link=link)
    data     = await state.get_data()
    svc_type = data.get("sp_type", "default")
    if svc_type == "package":
        await _show_confirm(msg, state); return
    if svc_type in ("custom_comments", "mentions_custom"):
        await state.set_state(SPState.order_extra)
        label = "کامنت‌ها (هر خط یک کامنت)" if svc_type == "custom_comments" else "یوزرنیم‌ها (هر خط یک یوزرنیم)"
        await msg.answer(f"✏️ <b>{label}:</b>\n\n/cancel برای لغو", parse_mode="HTML"); return
    await state.set_state(SPState.order_qty)
    min_q = data.get("sp_min", 1); max_q = data.get("sp_max", 1000000)
    sell_rate = data.get("sp_sell_rate", data.get("sp_rate", 0))
    await msg.answer(
        f"🔢 <b>تعداد را وارد کنید:</b>\n\nحداقل: <b>{min_q:,}</b>  |  حداکثر: <b>{max_q:,}</b>\n"
        f"💰 قیمت: <b>${sell_rate:.4f}</b> / هر ۱۰۰۰\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(SPState.order_extra)
async def sp_got_extra(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    await state.update_data(sp_extra=(msg.text or "").strip())
    await state.set_state(SPState.order_qty)
    data = await state.get_data()
    min_q = data.get("sp_min", 1); max_q = data.get("sp_max", 1000000)
    await msg.answer(
        f"🔢 تعداد را وارد کنید:\nحداقل: <b>{min_q:,}</b>  |  حداکثر: <b>{max_q:,}</b>\n\n/cancel برای لغو",
        parse_mode="HTML"
    )


@router.message(SPState.order_qty)
async def sp_got_qty(msg: Message, state: FSMContext, db_user: User = None):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        qty = int((msg.text or "").strip().replace(",", "").replace("\u060c", ""))
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید."); return
    data = await state.get_data()
    min_q = data.get("sp_min", 1); max_q = data.get("sp_max", 1000000)
    if qty < min_q or qty > max_q:
        await msg.answer(f"❌ تعداد باید بین {min_q:,} و {max_q:,} باشد."); return
    await state.update_data(sp_qty=qty)
    await _show_confirm(msg, state, db_user=db_user)


async def _show_confirm(msg: Message, state: FSMContext, db_user: User = None):
    data      = await state.get_data()
    name      = data.get("sp_svc_name", "")
    link      = data.get("sp_link", "")
    qty       = data.get("sp_qty", 1)
    rate      = data.get("sp_rate", 0)
    markup    = data.get("sp_markup", 0.0)
    total     = _total(rate, qty, markup)
    bal    = float(db_user.balance or 0) if db_user else 0
    bal_ok = bal >= total
    text = (
        f"📋 <b>تایید سفارش</b>\n\n"
        f"🛒 سرویس: <b>{name[:45]}</b>\n"
        f"🔗 لینک: <code>{link}</code>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        f"💰 هزینه: <b>${total:.4f}</b>\n"
        f"💳 موجودی: <b>${bal:.2f}</b>\n\n"
    )
    text += "✅ موجودی کافی است." if bal_ok else "❌ موجودی ناکافی — ابتدا شارژ کنید."
    rows = []
    if bal_ok:
        rows.append([InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="sp_confirm")])
    else:
        rows.append([InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")])
    rows.append([InlineKeyboardButton(text="❌ لغو", callback_data="sp_cancel")])
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


# ── Confirm & Place ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_confirm")
async def sp_confirm(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    await cb.answer()
    data     = await state.get_data()
    svc_id   = data.get("sp_svc_id")
    svc_name = data.get("sp_svc_name", "")
    link     = data.get("sp_link", "")
    qty      = data.get("sp_qty", 1)
    rate     = data.get("sp_rate", 0)
    markup   = data.get("sp_markup", 0.0)
    svc_type = data.get("sp_type", "default")
    extra    = data.get("sp_extra", "")
    total    = _total(rate, qty, markup)
    if not svc_id:
        await cb.message.edit_text(
            "❌ اطلاعات سفارش یافت نشد. دوباره از ابتدا سفارش دهید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")]
            ])
        )
        await state.clear(); return
    bal = float(db_user.balance or 0) if db_user else 0
    if bal < total:
        await cb.message.edit_text(
            "❌ <b>موجودی ناکافی!</b>\nلطفاً ابتدا موجودی خود را شارژ کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")],
                [InlineKeyboardButton(text="🏠 بازگشت",       callback_data="user_home")],
            ]),
            parse_mode="HTML"
        ); return
    await cb.message.edit_text("⏳ در حال ثبت سفارش...")
    async with AsyncSessionLocal() as session:
        ok = await deduct_balance(session, db_user.id, total)
        if not ok:
            await cb.message.edit_text("❌ خطا در کسر موجودی. دوباره تلاش کنید."); return
        await session.commit()
        try:
            if svc_type == "package":
                res = await add_order_package(int(svc_id), link)
            elif svc_type == "custom_comments":
                res = await add_order_custom_comments(int(svc_id), link, extra)
            elif svc_type == "mentions_custom":
                res = await add_order_mentions_custom(int(svc_id), link, extra)
            elif svc_type == "mentions_hashtag":
                res = await add_order_mentions_hashtag(int(svc_id), link, qty)
            elif svc_type == "subscription":
                res = await add_order_subscription(int(svc_id), link, data.get("sp_sub_min", 1), qty)
            else:
                res = await add_order_default(int(svc_id), link, qty)
            ext_id = str(res.get("order", ""))
        except Exception as e:
            await add_balance(session, db_user.id, total)
            await session.commit()
            await cb.message.edit_text(
                f"❌ <b>خطا در API:</b>\n<code>{str(e)[:200]}</code>\n\nموجودی برگردانده شد.",
                parse_mode="HTML"
            ); return
        order = await create_order(
            session, user_id=db_user.id, service_id=int(svc_id),
            service_name=svc_name, link=link, quantity=qty,
            cost_price=round(rate * qty / 1000, 6), sell_price=total,  # sell includes markup
        )
    await state.clear()
    await cb.message.edit_text(
        f"✅ <b>سفارش ثبت شد!</b>\n\n"
        f"🆔 شناسه: <b>#{order.id}</b>\n"
        f"🌐 شناسه API: <code>{ext_id}</code>\n"
        f"🛒 سرویس: <b>{svc_name[:40]}</b>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        f"💰 پرداخت: <b>${total:.4f}</b>\n\n"
        "⏳ سفارش در صف پردازش است.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 سفارشات من", callback_data="sp_my_orders")],
            [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
            [InlineKeyboardButton(text="🏠 خانه",        callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "sp_cancel")
async def sp_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("لغو شد.")
    await cb.message.edit_text(
        "❌ سفارش لغو شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 بازگشت", callback_data="menu_smmpass")]
        ])
    )


# ── Subscription ──────────────────────────────────────────────────────────────
@router.message(SPState.sub_username)
async def sp_sub_user(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    await state.update_data(sp_link=msg.text.strip().lstrip("@"))
    await state.set_state(SPState.sub_min)
    await msg.answer("🔢 حداقل تعداد در روز:\n\n/cancel برای لغو")

@router.message(SPState.sub_min)
async def sp_sub_min(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        mn = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید."); return
    await state.update_data(sp_sub_min=mn)
    await state.set_state(SPState.sub_max)
    await msg.answer("🔢 حداکثر تعداد در روز:\n\n/cancel برای لغو")

@router.message(SPState.sub_max)
async def sp_sub_max(msg: Message, state: FSMContext, db_user: User = None):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        mx = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید."); return
    await state.update_data(sp_qty=mx)
    await _show_confirm(msg, state, db_user=db_user)


# ── Status check ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_check_status")
async def sp_check_status_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(SPState.check_status)
    await cb.message.edit_text(
        "🔍 <b>وضعیت سفارش</b>\n\nشناسه سفارش API را وارد کنید:\n\n/cancel برای لغو",
        parse_mode="HTML"
    )

@router.message(SPState.check_status)
async def sp_check_status_handle(msg: Message, state: FSMContext):
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("❌ لغو شد."); return
    try:
        oid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ شناسه عددی وارد کنید."); return
    await state.clear()
    try:
        r      = await get_order_status(oid)
        status = r.get("status", "?")
        icon   = STATUS_ICONS.get(str(status).lower(), "🟡")
        await msg.answer(
            f"📦 <b>سفارش #{oid}</b>\n\n"
            f"{icon} وضعیت: <b>{status}</b>\n"
            f"💰 هزینه: <b>{r.get('charge','?')}</b>\n"
            f"🔢 شروع: <b>{r.get('start_count','?')}</b>  |  باقی‌مانده: <b>{r.get('remains','?')}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 بازگشت", callback_data="menu_smmpass")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.answer(f"❌ خطا: {e}")


# ── My orders ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "sp_my_orders")
async def sp_my_orders(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, db_user.id)
    if not orders:
        await cb.message.edit_text(
            "📦 هنوز سفارشی ثبت نکرده‌اید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
                [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="menu_smmpass")],
            ])
        ); return
    lines = []
    for o in orders[:15]:
        icon = STATUS_ICONS.get(o.status, "🟡")
        lines.append(
            f"{icon} <b>#{o.id}</b>  {o.service_name[:25]}\n"
            f"   🔢 {o.quantity:,}  💰 ${float(o.sell_price):.4f}  📅 {o.created_at.strftime('%m/%d %H:%M')}"
        )
    await cb.message.edit_text(
        "📦 <b>سفارشات من</b>\n\n" + "\n\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
            [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="menu_smmpass")],
        ]),
        parse_mode="HTML"
    )
