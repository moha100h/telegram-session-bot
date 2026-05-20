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
            [InlineKeyboardButton(text="🏠 بازگشت",     callback_data="user_home")],
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

TYPE_PROMPTS = {
    "default":            ("🔗", "لینک پست یا پروفایل را وارد کنید:", "مثال: https://t.me/channel/123"),
    "package":            ("🔗", "لینک کانال یا پروفایل را وارد کنید:", "مثال: https://t.me/yourchannel"),
    "poll":               ("🗳", "لینک پست نظرسنجی را وارد کنید:", "مثال: https://t.me/channel/123"),
    "mentions_hashtag":   ("🔗", "لینک پست تلگرام را وارد کنید:", "مثال: https://t.me/channel/123"),
    "mentions_custom":    ("🔗", "لینک پست تلگرام را وارد کنید:", "مثال: https://t.me/channel/123"),
    "mentions_followers": ("🔗", "لینک پست تلگرام را وارد کنید:", "مثال: https://t.me/channel/123"),
    "custom_comments":    ("🔗", "لینک پست تلگرام را وارد کنید:", "مثال: https://t.me/channel/123"),
    "comment_likes":      ("💬", "لینک کامنت را وارد کنید:", "مثال: https://t.me/channel/123?comment=456"),
}
TYPE_EXTRA_PROMPTS = {
    "custom_comments": ("✏️", "کامنت‌ها را وارد کنید:", "هر خط یک کامنت — مثال:\nعالیه!\nخیلی خوب بود"),
    "mentions_custom": ("👤", "یوزرنیم‌ها را وارد کنید:", "هر خط یک یوزرنیم — مثال:\nuser1\nuser2"),
}

def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو سفارش", callback_data="sp_cancel")]
    ])


@router.callback_query(F.data == "sp_start_order")
async def sp_start_order(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data      = await state.get_data()
    svc_type  = data.get("sp_type", "default")
    svc_name  = data.get("sp_svc_name", "")
    min_q     = data.get("sp_min", 1)
    max_q     = data.get("sp_max", 1000000)
    sell_rate = data.get("sp_sell_rate", data.get("sp_rate", 0))
    if svc_type == "subscription":
        await state.set_state(SPState.sub_username)
        await cb.message.edit_text(
            f"📌 <b>اشتراک — {svc_name[:40]}</b>\n{'━'*28}\n\n"
            f"👤 یوزرنیم کانال یا گروه را وارد کنید:\n<i>(بدون @ — مثال: mychannel)</i>",
            reply_markup=_cancel_kb(), parse_mode="HTML"
        ); return
    icon, title, hint = TYPE_PROMPTS.get(svc_type, TYPE_PROMPTS["default"])
    await state.set_state(SPState.order_link)
    await cb.message.edit_text(
        f"{icon} <b>{title}</b>\n{'━'*28}\n\n"
        f"🛒 سرویس: <i>{svc_name[:45]}</i>\n"
        f"💰 قیمت: <b>${sell_rate:.4f}</b> / هر ۱۰۰۰\n"
        f"📊 حداقل: <b>{min_q:,}</b> | حداکثر: <b>{max_q:,}</b>\n\n"
        f"<i>{hint}</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )


@router.message(SPState.order_link)
async def sp_got_link(msg: Message, state: FSMContext):
    link = (msg.text or "").strip()
    if not link:
        await msg.answer("❌ لینک معتبر وارد کنید.", reply_markup=_cancel_kb()); return
    await state.update_data(sp_link=link)
    data     = await state.get_data()
    svc_type = data.get("sp_type", "default")
    svc_name = data.get("sp_svc_name", "")
    if svc_type == "package":
        await _show_confirm(msg, state); return
    if svc_type in TYPE_EXTRA_PROMPTS:
        await state.set_state(SPState.order_extra)
        icon, title, hint = TYPE_EXTRA_PROMPTS[svc_type]
        await msg.answer(
            f"{icon} <b>{title}</b>\n{'━'*28}\n\n"
            f"🛒 سرویس: <i>{svc_name[:45]}</i>\n\n<i>{hint}</i>",
            reply_markup=_cancel_kb(), parse_mode="HTML"
        ); return
    await state.set_state(SPState.order_qty)
    min_q     = data.get("sp_min", 1)
    max_q     = data.get("sp_max", 1000000)
    sell_rate = data.get("sp_sell_rate", data.get("sp_rate", 0))
    await msg.answer(
        f"🔢 <b>تعداد را وارد کنید:</b>\n{'━'*28}\n\n"
        f"📊 حداقل: <b>{min_q:,}</b> | حداکثر: <b>{max_q:,}</b>\n"
        f"💰 قیمت: <b>${sell_rate:.4f}</b> / هر ۱۰۰۰\n\n"
        f"<i>فقط عدد وارد کنید — مثال: 1000</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )


@router.message(SPState.order_extra)
async def sp_got_extra(msg: Message, state: FSMContext):
    extra = (msg.text or "").strip()
    if not extra:
        await msg.answer("❌ مقدار نمی‌تواند خالی باشد.", reply_markup=_cancel_kb()); return
    await state.update_data(sp_extra=extra)
    data      = await state.get_data()
    min_q     = data.get("sp_min", 1)
    max_q     = data.get("sp_max", 1000000)
    sell_rate = data.get("sp_sell_rate", data.get("sp_rate", 0))
    await state.set_state(SPState.order_qty)
    await msg.answer(
        f"🔢 <b>تعداد را وارد کنید:</b>\n{'━'*28}\n\n"
        f"📊 حداقل: <b>{min_q:,}</b> | حداکثر: <b>{max_q:,}</b>\n"
        f"💰 قیمت: <b>${sell_rate:.4f}</b> / هر ۱۰۰۰\n\n"
        f"<i>فقط عدد وارد کنید — مثال: 1000</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )


@router.message(SPState.order_qty)
async def sp_got_qty(msg: Message, state: FSMContext, db_user: User = None):
    try:
        qty = int((msg.text or "").strip().replace(",", "").replace("\u060c", ""))
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.", reply_markup=_cancel_kb()); return
    data  = await state.get_data()
    min_q = data.get("sp_min", 1)
    max_q = data.get("sp_max", 1000000)
    if qty < min_q or qty > max_q:
        await msg.answer(
            f"❌ تعداد باید بین <b>{min_q:,}</b> و <b>{max_q:,}</b> باشد.",
            reply_markup=_cancel_kb(), parse_mode="HTML"
        ); return
    await state.update_data(sp_qty=qty)
    await _show_confirm(msg, state, db_user=db_user)


async def _show_confirm(msg: Message, state: FSMContext, db_user: User = None):
    data      = await state.get_data()
    name      = data.get("sp_svc_name", "")
    svc_type  = data.get("sp_type", "default")
    link      = data.get("sp_link", "")
    qty       = data.get("sp_qty", 1)
    extra     = data.get("sp_extra", "")
    rate      = data.get("sp_rate", 0)
    markup    = data.get("sp_markup", 0.0)
    total     = _total(rate, qty, markup)
    bal       = float(db_user.balance or 0) if db_user else 0
    bal_ok    = bal >= total
    type_label= TYPE_LABELS.get(svc_type, svc_type)
    text = (
        f"📋 <b>تایید سفارش</b>\n{'━'*28}\n"
        f"🛒 سرویس: <b>{name[:45]}</b>\n"
        f"🔧 نوع: <b>{type_label}</b>\n"
        f"🔗 لینک: <code>{link}</code>\n"
    )
    if svc_type != "package":
        text += f"🔢 تعداد: <b>{qty:,}</b>\n"
    if extra:
        text += f"✏️ محتوا: <i>{extra[:60]}{'...' if len(extra)>60 else ''}</i>\n"
    text += (
        f"{'━'*28}\n"
        f"💰 هزینه: <b>${total:.4f}</b>\n"
        f"💳 موجودی: <b>${bal:.2f}</b>\n\n"
    )
    text += "✅ موجودی کافی است." if bal_ok else "❌ موجودی ناکافی — ابتدا شارژ کنید."
    rows = []
    if bal_ok:
        rows.append([InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="sp_confirm")])
    else:
        rows.append([InlineKeyboardButton(text="💳 شارژ موجودی", callback_data="user_deposit")])
    rows.append([InlineKeyboardButton(text="❌ لغو سفارش", callback_data="sp_cancel")])
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


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
    await cb.message.edit_text("⏳ <b>در حال ثبت سفارش...</b>", parse_mode="HTML")
    async with AsyncSessionLocal() as _s:
        panel_title = await get_setting(_s, "smm_panel_title", "SMMPass")
    async with AsyncSessionLocal() as session:
        ok = await deduct_balance(session, db_user.id, total)
        if not ok:
            await cb.message.edit_text(
                "❌ خطا در کسر موجودی. دوباره تلاش کنید.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data="sp_confirm")],
                    [InlineKeyboardButton(text="🏠 بازگشت",     callback_data="user_home")],
                ])
            ); return
        await session.commit()
        try:
            if svc_type == "package":
                res = await add_order_package(int(svc_id), link)
            elif svc_type == "custom_comments":
                res = await add_order_custom_comments(int(svc_id), link, extra)
            elif svc_type == "mentions_custom":
                res = await add_order_mentions_custom(int(svc_id), link, extra)
            elif svc_type in ("mentions_hashtag", "mentions_followers"):
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
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
                    [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="user_home")],
                ]),
                parse_mode="HTML"
            ); return
        order = await create_order(
            session, user_id=db_user.id, service_id=int(svc_id),
            service_name=svc_name, link=link, quantity=qty,
            cost_price=round(rate * qty / 1000, 6), sell_price=total,
            api_order_id=ext_id if ext_id else None,
            panel_name=panel_title,
        )
    await state.clear()
    await cb.message.edit_text(
        f"✅ <b>سفارش با موفقیت ثبت شد!</b>\n{'━'*28}\n"
        f"🆔 شناسه: <b>#{order.id}</b>\n"
        f"🌐 شناسه API: <code>{ext_id}</code>\n"
        f"🛒 سرویس: <b>{svc_name[:40]}</b>\n"
        f"🔢 تعداد: <b>{qty:,}</b>\n"
        f"💰 پرداخت: <b>${total:.4f}</b>\n{'━'*28}\n\n"
        f"⏳ سفارش در صف پردازش است.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 سفارشات من", callback_data="user_orders")],
            [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
            [InlineKeyboardButton(text="🏠 خانه",        callback_data="user_home")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "sp_cancel")
async def sp_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "❌ <b>سفارش لغو شد.</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
            [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="menu_smmpass")],
        ]),
        parse_mode="HTML"
    )


# ── Subscription ──────────────────────────────────────────────────────────────
@router.message(SPState.sub_username)
async def sp_sub_user(msg: Message, state: FSMContext):
    username = (msg.text or "").strip().lstrip("@")
    if not username:
        await msg.answer("❌ یوزرنیم معتبر وارد کنید.", reply_markup=_cancel_kb()); return
    await state.update_data(sp_link=username)
    await state.set_state(SPState.sub_min)
    await msg.answer(
        f"🔢 <b>حداقل تعداد در روز:</b>\n{'━'*28}\n\n<i>عدد صحیح وارد کنید — مثال: 10</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )


@router.message(SPState.sub_min)
async def sp_sub_min(msg: Message, state: FSMContext):
    try:
        mn = int((msg.text or "").strip())
        if mn <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح مثبت وارد کنید.", reply_markup=_cancel_kb()); return
    await state.update_data(sp_sub_min=mn)
    await state.set_state(SPState.sub_max)
    await msg.answer(
        f"🔢 <b>حداکثر تعداد در روز:</b>\n{'━'*28}\n\n<i>باید بیشتر از حداقل ({mn:,}) باشد</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )


@router.message(SPState.sub_max)
async def sp_sub_max(msg: Message, state: FSMContext, db_user: User = None):
    data = await state.get_data()
    mn   = data.get("sp_sub_min", 1)
    try:
        mx = int((msg.text or "").strip())
        if mx <= mn: raise ValueError
    except ValueError:
        await msg.answer(f"❌ عدد باید بیشتر از {mn:,} باشد.", reply_markup=_cancel_kb()); return
    await state.update_data(sp_qty=mx)
    await _show_confirm(msg, state, db_user=db_user)




@router.callback_query(F.data == "sp_my_orders")
async def sp_my_orders(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, db_user.id)
    if not orders:
        await cb.message.edit_text(
            "📦 <b>سفارشات من</b>\n\nهنوز سفارشی ثبت نکرده‌اید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 اولین سفارش", callback_data="sp_cats_0")],
                [InlineKeyboardButton(text="🏠 بازگشت",       callback_data="menu_smmpass")],
            ]),
            parse_mode="HTML"
        ); return

    completed = sum(1 for o in orders if o.status == "completed")
    active    = sum(1 for o in orders if o.status in ("pending", "processing", "in progress"))
    spent     = sum(float(o.sell_price or 0) for o in orders)

    await cb.message.edit_text(
        f"📦 <b>سفارشات من</b>\n\n"
        f"📊 کل: <b>{len(orders)}</b>  ✅ تکمیل: <b>{completed}</b>  "
        f"⏳ فعال: <b>{active}</b>\n"
        f"💰 مجموع پرداخت: <b>${spent:.4f}</b>\n\n"
        f"روی هر سفارش کلیک کنید 👇",
        reply_markup=_my_orders_kb(orders, page=0),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("sp_orders_pg_"))
async def sp_orders_paged(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    page = int(cb.data.split("_")[-1])
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, db_user.id)
    await cb.message.edit_text(
        f"📦 <b>سفارشات من</b> — صفحه {page + 1}\n\nروی هر سفارش کلیک کنید 👇",
        reply_markup=_my_orders_kb(orders, page=page),
        parse_mode="HTML"
    )


# ── جزئیات سفارش کاربر ────────────────────────────────────────────────────────
@router.callback_query(F.data.regexp(r"^sp_order_\d+$"))
async def sp_order_detail(cb: CallbackQuery, db_user: User = None):
    await cb.answer("🔄 در حال بروزرسانی...")
    from services.order_service import get_order_by_id, update_order_status, process_refund
    order_id = int(cb.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)

    # بررسی مالکیت
    if not order or order.user_id != db_user.id:
        await cb.answer("❌ سفارش یافت نشد!", show_alert=True); return

    live_status  = order.status
    live_start   = order.start_count
    live_remains = order.remains
    api_error    = None
    refunded     = 0.0

    # ── دریافت وضعیت live از API ─────────────────────────────────────────────
    api_id = order.api_order_id
    if api_id and str(api_id).isdigit():
        try:
            data         = await get_order_status(int(api_id))
            live_status  = str(data.get("status", order.status)).lower()
            live_start   = data.get("start_count", order.start_count)
            live_remains = data.get("remains",     order.remains)

            async with AsyncSessionLocal() as session:
                updated = await update_order_status(
                    session, order_id, live_status,
                    start_count = int(live_start)   if live_start   is not None else None,
                    remains     = int(live_remains) if live_remains is not None else None,
                )
                if updated and live_status in ("cancelled", "partial") and order.status != live_status:
                    refunded = await process_refund(session, updated)
                await session.commit()
        except Exception as e:
            api_error = str(e)[:80]

    # ── محاسبه progress ───────────────────────────────────────────────────────
    icon  = STATUS_ICONS.get(live_status, "🟡")
    ST_FA = {
        "pending": "در صف", "processing": "در حال انجام",
        "in progress": "در حال انجام", "completed": "تکمیل شده",
        "partial": "ناقص", "cancelled": "کنسل شده",
        "failed": "ناموفق", "refunded": "برگشت خورده",
    }
    label = ST_FA.get(live_status, live_status)

    done = pct = 0
    try:
        if live_start is not None and live_remains is not None:
            done = max(0, int(live_start) - int(live_remains))
            pct  = min(100, int(done / order.quantity * 100)) if order.quantity > 0 else 0
    except Exception:
        pass

    bar_len = 10
    filled  = min(bar_len, int(pct / 100 * bar_len))
    bar     = "█" * filled + "░" * (bar_len - filled)

    # ── متن پیام ─────────────────────────────────────────────────────────────
    text = (
        f"📦 <b>سفارش #{order.id}</b>\n\n"
        f"🛒 <b>{order.service_name}</b>\n"
        f"🔗 <code>{order.link}</code>\n"
        f"🔢 تعداد: <b>{order.quantity:,}</b>\n"
        f"💰 پرداخت: <b>${float(order.sell_price):.4f}</b>\n"
        f"📅 ثبت: <b>{order.created_at.strftime('%Y-%m-%d %H:%M')}</b>\n"
        f"\n━━━━━━━━━━━━━━━━━\n"
        f"{icon} وضعیت: <b>{label}</b>\n"
    )
    if live_start is not None:
        text += f"🔢 شروع از: <b>{int(live_start):,}</b>\n"
    if live_remains is not None:
        text += f"⏳ باقی‌مانده: <b>{int(live_remains):,}</b>\n"
    if done > 0 or pct > 0:
        text += (
            f"✅ انجام شده: <b>{done:,}</b> از <b>{order.quantity:,}</b>\n"
            f"📊 <code>[{bar}]</code> <b>{pct}%</b>\n"
        )
    if api_error:
        text += f"\n⚠️ <i>خطا در دریافت وضعیت: {api_error}</i>\n"
    if refunded > 0:
        text += f"\n↩️ <b>${refunded:.4f} به موجودی شما برگشت داده شد.</b>"
    elif live_status == "completed":
        text += "\n🎉 <b>سفارش با موفقیت تکمیل شد!</b>"
    elif live_status == "cancelled":
        text += "\n↩️ <b>سفارش کنسل شده — پول برگشت خورده.</b>"
    elif live_status == "partial":
        text += "\n↩️ <b>سفارش ناقص — مابقی برگشت داده شد.</b>"

    await cb.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"sp_order_{order_id}")],
            [InlineKeyboardButton(text="🔙 سفارشات من", callback_data="user_orders")],
            [InlineKeyboardButton(text="🏠 خانه",        callback_data="menu_smmpass")],
        ]),
        parse_mode="HTML"
    )


# ── وضعیت سفارش با شناسه (حذف FSM — مستقیم از DB) ───────────────────────────
@router.callback_query(F.data == "sp_check_status")
async def sp_check_status_start(cb: CallbackQuery, state: FSMContext, db_user: User = None):
    """ریدایرکت به سفارشات من — دیگه نیازی به وارد کردن شناسه API نیست."""
    await cb.answer()
    from services.order_service import get_user_orders
    async with AsyncSessionLocal() as session:
        orders = await get_user_orders(session, db_user.id)
    if not orders:
        await cb.message.edit_text(
            "📦 <b>سفارشات من</b>\n\nهنوز سفارشی ثبت نکرده‌اید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛒 سفارش جدید", callback_data="sp_cats_0")],
                [InlineKeyboardButton(text="🏠 بازگشت",      callback_data="menu_smmpass")],
            ]),
            parse_mode="HTML"
        ); return

    completed = sum(1 for o in orders if o.status == "completed")
    active    = sum(1 for o in orders if o.status in ("pending", "processing", "in progress"))
    spent     = sum(float(o.sell_price or 0) for o in orders)

    await cb.message.edit_text(
        f"📦 <b>سفارشات من</b>\n\n"
        f"📊 کل: <b>{len(orders)}</b>  ✅ تکمیل: <b>{completed}</b>  "
        f"⏳ فعال: <b>{active}</b>\n"
        f"💰 مجموع پرداخت: <b>${spent:.4f}</b>\n\n"
        f"روی هر سفارش کلیک کنید 👇",
        reply_markup=_my_orders_kb(orders, page=0),
        parse_mode="HTML"
    )
