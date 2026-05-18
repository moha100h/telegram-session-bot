"""
Panel Admin Handler — مدیریت پنل‌های دستی از طرف ادمین.
ایجاد پنل، دسته‌بندی، خدمات + مدیریت سفارش‌ها از گروه.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from db.database import AsyncSessionLocal
from services.panel_service import (
    get_all_panels, get_panel, create_panel, update_panel, delete_panel,
    get_categories, create_category, update_category, delete_category,
    get_services, get_service, create_service, update_service, delete_service,
    get_panel_order, update_panel_order_status, process_panel_refund,
)
from services.notification_service import notify_order_status, notify_refund

logger = logging.getLogger("panel_admin")
router = Router()


def _parse_price(text: str) -> float:
    """تبدیل قیمت — پشتیبانی از اعداد فارسی، کاما، نقطه"""
    FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                       "01234567890123456789")
    t = (text or "").strip().translate(FA)
    if t.count(",") == 1 and t.count(".") == 0:
        parts = t.split(",")
        if len(parts[1]) <= 4:
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    else:
        t = t.replace(",", "")
    return float(t)

import os
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

async def _is_admin(uid: int) -> bool:
    from services.user_service import is_admin as _ia
    async with AsyncSessionLocal() as s:
        return await _ia(s, uid) or uid == ADMIN_ID


# ── States ────────────────────────────────────────────────────────────────────
class PanelAdminState(StatesGroup):
    # ایجاد پنل
    panel_name         = State()
    panel_button_label = State()
    panel_description  = State()
    panel_group_id     = State()
    # ایجاد دسته
    cat_name           = State()
    cat_icon           = State()
    # ایجاد خدمت
    svc_name           = State()
    svc_desc           = State()
    svc_price          = State()
    svc_min            = State()
    svc_max            = State()
    # ویرایش
    edit_value         = State()
    # partial refund
    partial_qty        = State()
    grp_partial_qty = State()  # عدد تکمیل جزئی از گروه


class PanelOrderSearchState(StatesGroup):
    query = State()


# ── helpers ───────────────────────────────────────────────────────────────────
def _back(cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]
    ])

def _cancel_kb(back_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو", callback_data=back_cb)]
    ])

STATUS_FA = {
    "pending":    ("⏳", "در انتظار"),
    "processing": ("🔄", "در حال انجام"),
    "completed":  ("✅", "تکمیل شد"),
    "partial":    ("⚠️", "تکمیل جزئی"),
    "rejected":   ("❌", "رد شد"),
}


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۱ — لیست پنل‌ها
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_panels")
async def adm_panels(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as s:
        panels = await get_all_panels(s)
    rows = []
    # SMMPass — پنل اتوماتیک (همیشه اول)
    rows.append([InlineKeyboardButton(
        text="🚀 SMMPass (اتوماتیک)",
        callback_data="adm_smmpass"
    )])
    # پنل‌های دستی
    for p in panels:
        icon = "✅" if p.is_active else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{icon} {p.button_label} — {p.name}",
            callback_data=f"adm_panel_{p.id}"
        )])
    rows.append([InlineKeyboardButton(text="➕ ایجاد پنل دستی جدید", callback_data="adm_panel_create")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_admin")])
    await cb.message.edit_text(
        f"🎛 <b>مدیریت پنل‌ها</b>\n{'━'*28}\n"
        f"🚀 SMMPass: پنل اتوماتیک\n"
        f"🎛 پنل‌های دستی: <b>{len(panels)}</b>\n\n"
        "یک پنل را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۲ — ایجاد پنل (مرحله‌ای)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_panel_create")
async def adm_panel_create(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    await state.set_state(PanelAdminState.panel_name)
    await cb.message.edit_text(
        "➕ <b>ایجاد پنل جدید — مرحله ۱/۴</b>\n{'━'*28}\n\n"
        "📝 <b>اسم داخلی پنل را وارد کنید:</b>\n"
        "<i>(فقط برای ادمین — مثال: پنل ویژه VIP)</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.panel_name)
async def adm_panel_name(msg: Message, state: FSMContext):
    name = (msg.text or "").strip()
    if not name: await msg.answer("❌ اسم نمی‌تواند خالی باشد.", reply_markup=_cancel_kb("adm_panels")); return
    await state.update_data(panel_name=name)
    await state.set_state(PanelAdminState.panel_button_label)
    await msg.answer(
        "➕ <b>ایجاد پنل جدید — مرحله ۲/۴</b>\n{'━'*28}\n\n"
        "🔘 <b>متن دکمه کاربر را وارد کنید:</b>\n"
        "<i>(این متن در منوی کاربر نمایش داده می‌شود — مثال: 💎 پنل ویژه)</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.panel_button_label)
async def adm_panel_button(msg: Message, state: FSMContext):
    label = (msg.text or "").strip()
    if not label: await msg.answer("❌ متن دکمه نمی‌تواند خالی باشد.", reply_markup=_cancel_kb("adm_panels")); return
    await state.update_data(panel_button_label=label)
    await state.set_state(PanelAdminState.panel_description)
    await msg.answer(
        "➕ <b>ایجاد پنل جدید — مرحله ۳/۴</b>\n{'━'*28}\n\n"
        "📄 <b>توضیح کوتاه پنل:</b>\n"
        "<i>(اختیاری — برای نمایش به کاربر. برای رد کردن /skip بزنید)</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.panel_description)
async def adm_panel_desc(msg: Message, state: FSMContext):
    desc = "" if (msg.text or "").strip() == "/skip" else (msg.text or "").strip()
    await state.update_data(panel_description=desc)
    await state.set_state(PanelAdminState.panel_group_id)
    await msg.answer(
        "➕ <b>ایجاد پنل جدید — مرحله ۴/۴</b>\n{'━'*28}\n\n"
        "👥 <b>آیدی گروه تلگرام برای نمایش سفارش‌ها:</b>\n"
        "<i>(بات را به گروه اضافه کنید، سپس آیدی گروه را بفرستید.\n"
        "مثال: -1001234567890\n"
        "برای رد کردن /skip بزنید)</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.panel_group_id)
async def adm_panel_group(msg: Message, state: FSMContext):
    text = (msg.text or "").strip()
    group_id = None
    if text != "/skip":
        try:
            group_id = int(text)
        except ValueError:
            await msg.answer("❌ آیدی گروه باید عدد باشد. مثال: -1001234567890",
                             reply_markup=_cancel_kb("adm_panels")); return
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as s:
        panel = await create_panel(s, data["panel_name"], data["panel_button_label"],
                                   data.get("panel_description",""), group_id)
        await s.commit()
        pid = panel.id
    await msg.answer(
        f"✅ <b>پنل ایجاد شد!</b>\n{'━'*28}\n"
        f"🆔 شناسه: <b>#{pid}</b>\n"
        f"📝 اسم: <b>{data['panel_name']}</b>\n"
        f"🔘 دکمه: <b>{data['panel_button_label']}</b>\n"
        f"👥 گروه: <b>{group_id or 'تنظیم نشده'}</b>\n\n"
        "حالا می‌توانید دسته‌بندی اضافه کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن دسته‌بندی", callback_data=f"adm_panel_addcat_{pid}")],
            [InlineKeyboardButton(text="🔙 لیست پنل‌ها",     callback_data="adm_panels")],
        ]),
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۳ — مدیریت پنل (جزئیات)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^adm_panel_\d+$"))
async def adm_panel_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    pid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        panel = await get_panel(s, pid)
        cats  = await get_categories(s, pid)
    if not panel:
        await cb.message.edit_text("❌ پنل یافت نشد.", reply_markup=_back("adm_panels")); return
    status = "✅ فعال" if panel.is_active else "🔴 غیرفعال"
    rows = []
    for cat in cats:
        rows.append([InlineKeyboardButton(
            text=f"{cat.icon} {cat.name}",
            callback_data=f"adm_pcat_{cat.id}"
        )])
    rows += [
        [InlineKeyboardButton(text="➕ افزودن دسته‌بندی", callback_data=f"adm_panel_addcat_{pid}")],
        [InlineKeyboardButton(text="📦 سفارشات ۲۴ ساعت",  callback_data=f"adm_panel_orders_{pid}")],
        [InlineKeyboardButton(text="✏️ ویرایش دکمه",      callback_data=f"adm_panel_editlabel_{pid}"),
         InlineKeyboardButton(text="👥 تنظیم گروه",        callback_data=f"adm_panel_setgroup_{pid}")],
        [InlineKeyboardButton(
            text="🔴 غیرفعال کردن" if panel.is_active else "✅ فعال کردن",
            callback_data=f"adm_panel_toggle_{pid}"
        ),
         InlineKeyboardButton(text="🗑 حذف پنل",           callback_data=f"adm_panel_del_{pid}")],
        [InlineKeyboardButton(text="🔙 بازگشت",             callback_data="adm_panels")],
    ]
    await cb.message.edit_text(
        f"🎛 <b>{panel.button_label}</b>\n{'━'*28}\n"
        f"📝 اسم داخلی: <b>{panel.name}</b>\n"
        f"📊 وضعیت: {status}\n"
        f"👥 گروه: <code>{panel.group_chat_id or 'تنظیم نشده'}</code>\n"
        f"📂 دسته‌بندی‌ها: <b>{len(cats)}</b>\n"
        + (f"📄 توضیح: <i>{panel.description}</i>\n" if panel.description else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


@router.callback_query(F.data.regexp(r"^adm_panel_toggle_\d+$"))
async def adm_panel_toggle(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        panel = await get_panel(s, pid)
        if panel:
            await update_panel(s, pid, is_active=not panel.is_active)
            await s.commit()
    await cb.answer("✅ وضعیت تغییر کرد")
    await adm_panel_detail(cb)


@router.callback_query(F.data.regexp(r"^adm_panel_del_\d+$"))
async def adm_panel_del_confirm(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    await cb.answer()
    await cb.message.edit_text(
        "⚠️ <b>آیا مطمئن هستید؟</b>\n\n"
        "حذف پنل، تمام دسته‌بندی‌ها و خدمات آن را نیز حذف می‌کند!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 بله، حذف شود", callback_data=f"adm_panel_delok_{pid}"),
             InlineKeyboardButton(text="❌ لغو",           callback_data=f"adm_panel_{pid}")],
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data.regexp(r"^adm_panel_delok_\d+$"))
async def adm_panel_del_ok(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        await delete_panel(s, pid)
        await s.commit()
    await cb.answer("✅ پنل حذف شد")
    await adm_panels(cb)


@router.callback_query(F.data.regexp(r"^adm_panel_editlabel_\d+$"))
async def adm_panel_editlabel(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    await state.update_data(edit_panel_id=pid, edit_field="button_label")
    await state.set_state(PanelAdminState.edit_value)
    await cb.answer()
    await cb.message.edit_text(
        "✏️ <b>متن جدید دکمه را وارد کنید:</b>\n<i>مثال: 💎 پنل ویژه</i>",
        reply_markup=_cancel_kb(f"adm_panel_{pid}"),
        parse_mode="HTML"
    )

@router.callback_query(F.data.regexp(r"^adm_panel_setgroup_\d+$"))
async def adm_panel_setgroup(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    await state.update_data(edit_panel_id=pid, edit_field="group_chat_id")
    await state.set_state(PanelAdminState.edit_value)
    await cb.answer()
    await cb.message.edit_text(
        "👥 <b>آیدی گروه جدید را وارد کنید:</b>\n<i>مثال: -1001234567890</i>",
        reply_markup=_cancel_kb(f"adm_panel_{pid}"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.edit_value)
async def adm_panel_edit_value(msg: Message, state: FSMContext):
    data  = await state.get_data()
    pid   = data.get("edit_panel_id")
    field = data.get("edit_field")
    cat_id= data.get("edit_cat_id")
    svc_id= data.get("edit_svc_id")
    val   = (msg.text or "").strip()
    await state.clear()

    if field == "price":
        try:
            val = _parse_price(val)
            if val <= 0: raise ValueError
        except (ValueError, Exception):
            await msg.answer("❌ قیمت نامعتبر. مثال: 0.005 یا 2.50"); return
    elif field == "min_qty" or field == "max_qty":
        try: val = int(val)
        except ValueError:
            await msg.answer("❌ عدد صحیح وارد کنید."); return
    elif field == "group_chat_id":
        try: val = int(val)
        except ValueError:
            await msg.answer("❌ آیدی گروه باید عدد باشد."); return

    async with AsyncSessionLocal() as s:
        if svc_id:
            await update_service(s, svc_id, **{field: val})
        elif cat_id:
            await update_category(s, cat_id, **{field: val})
        elif pid:
            await update_panel(s, pid, **{field: val})
        await s.commit()
    # بازگشت هوشمند
    if svc_id:
        back_cb = f"adm_psvc_{svc_id}"
        back_txt = "🔙 بازگشت به خدمت"
    elif cat_id:
        back_cb = f"adm_pcat_{cat_id}"
        back_txt = "🔙 بازگشت به دسته"
    elif pid:
        back_cb = f"adm_panel_{pid}"
        back_txt = "🔙 بازگشت به پنل"
    else:
        back_cb = "adm_panels"
        back_txt = "🔙 بازگشت"
    await msg.answer(
        "✅ <b>تغییرات ذخیره شد.</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=back_txt, callback_data=back_cb)],
        ]),
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۴ — مدیریت دسته‌بندی
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^adm_panel_addcat_\d+$"))
async def adm_panel_addcat(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    await state.update_data(new_cat_panel_id=pid)
    await state.set_state(PanelAdminState.cat_name)
    await cb.answer()
    await cb.message.edit_text(
        "➕ <b>دسته‌بندی جدید — مرحله ۱/۲</b>\n{'━'*28}\n\n"
        "📂 <b>اسم دسته‌بندی را وارد کنید:</b>\n<i>مثال: ممبر تلگرام</i>",
        reply_markup=_cancel_kb(f"adm_panel_{pid}"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.cat_name)
async def adm_cat_name(msg: Message, state: FSMContext):
    name = (msg.text or "").strip()
    if not name: await msg.answer("❌ اسم نمی‌تواند خالی باشد."); return
    await state.update_data(new_cat_name=name)
    await state.set_state(PanelAdminState.cat_icon)
    await msg.answer(
        "➕ <b>دسته‌بندی جدید — مرحله ۲/۲</b>\n{'━'*28}\n\n"
        "🎨 <b>آیکون دسته را وارد کنید:</b>\n"
        "<i>یک ایموجی — مثال: 👥 یا 📈\n"
        "برای پیش‌فرض (📂) دستور /skip بزنید</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.cat_icon)
async def adm_cat_icon(msg: Message, state: FSMContext):
    icon = "📂" if (msg.text or "").strip() == "/skip" else (msg.text or "").strip()
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as s:
        cat = await create_category(s, data["new_cat_panel_id"], data["new_cat_name"], icon)
        await s.commit()
        cid = cat.id
        pid = data["new_cat_panel_id"]
    await msg.answer(
        f"✅ <b>دسته‌بندی ایجاد شد!</b>\n{'━'*28}\n"
        f"🆔 شناسه: <b>#{cid}</b>\n"
        f"{icon} <b>{data['new_cat_name']}</b>\n\n"
        "حالا می‌توانید خدمات اضافه کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن خدمت", callback_data=f"adm_pcat_addsvc_{cid}")],
            [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data=f"adm_panel_{pid}")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.regexp(r"^adm_pcat_\d+$"))
async def adm_pcat_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    cid = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import PanelCategory
    async with AsyncSessionLocal() as s:
        res = await s.execute(select(PanelCategory).where(PanelCategory.id == cid))
        cat  = res.scalar_one_or_none()
        svcs = await get_services(s, cid) if cat else []
    if not cat:
        await cb.message.edit_text("❌ دسته یافت نشد.", reply_markup=_back("adm_panels")); return
    rows = []
    for svc in svcs:
        st = "✅" if svc.is_active else "🔴"
        rows.append([InlineKeyboardButton(
            text=f"{st} {svc.name} — ${svc.price:.2f}",
            callback_data=f"adm_psvc_{svc.id}"
        )])
    rows += [
        [InlineKeyboardButton(text="➕ افزودن خدمت",   callback_data=f"adm_pcat_addsvc_{cid}")],
        [InlineKeyboardButton(text="✏️ ویرایش اسم",    callback_data=f"adm_pcat_editname_{cid}"),
         InlineKeyboardButton(text="🗑 حذف دسته",       callback_data=f"adm_pcat_del_{cid}")],
        [InlineKeyboardButton(text="🔙 بازگشت",         callback_data=f"adm_panel_{cat.panel_id}")],
    ]
    await cb.message.edit_text(
        f"{cat.icon} <b>{cat.name}</b>\n{'━'*28}\n"
        f"خدمات: <b>{len(svcs)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )

@router.callback_query(F.data.regexp(r"^adm_pcat_del_\d+$"))
async def adm_pcat_del(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    cid = int(cb.data.split("_")[-1])
    from sqlalchemy import select
    from db.models import PanelCategory
    async with AsyncSessionLocal() as s:
        res = await s.execute(select(PanelCategory).where(PanelCategory.id == cid))
        cat = res.scalar_one_or_none()
        pid = cat.panel_id if cat else 0
        await delete_category(s, cid)
        await s.commit()
    await cb.answer("✅ دسته حذف شد")
    # برگشت به پنل
    cb.data = f"adm_panel_{pid}"
    await adm_panel_detail(cb)

@router.callback_query(F.data.regexp(r"^adm_pcat_editname_\d+$"))
async def adm_pcat_editname(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    cid = int(cb.data.split("_")[-1])
    await state.update_data(edit_cat_id=cid, edit_field="name")
    await state.set_state(PanelAdminState.edit_value)
    await cb.answer()
    await cb.message.edit_text(
        "✏️ <b>اسم جدید دسته‌بندی را وارد کنید:</b>",
        reply_markup=_cancel_kb(f"adm_pcat_{cid}"),
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۵ — مدیریت خدمات
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^adm_pcat_addsvc_\d+$"))
async def adm_pcat_addsvc(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    cid = int(cb.data.split("_")[-1])
    await state.update_data(new_svc_cat_id=cid)
    await state.set_state(PanelAdminState.svc_name)
    await cb.answer()
    await cb.message.edit_text(
        "➕ <b>خدمت جدید — مرحله ۱/۴</b>\n{'━'*28}\n\n"
        "📌 <b>اسم خدمت را وارد کنید:</b>\n<i>مثال: ممبر واقعی ایرانی</i>",
        reply_markup=_cancel_kb(f"adm_pcat_{cid}"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.svc_name)
async def adm_svc_name(msg: Message, state: FSMContext):
    name = (msg.text or "").strip()
    if not name: await msg.answer("❌ اسم نمی‌تواند خالی باشد."); return
    await state.update_data(new_svc_name=name)
    await state.set_state(PanelAdminState.svc_price)
    await msg.answer(
        "➕ <b>خدمت جدید — مرحله ۲/۴</b>\n{'━'*28}\n\n"
        "💰 <b>قیمت هر واحد را وارد کنید (دلار):</b>\n"
        "<i>مثال: 0.5 یا 2.00</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.svc_price)
async def adm_svc_price(msg: Message, state: FSMContext):
    try:
        price = _parse_price(msg.text or "")
        if price <= 0: raise ValueError
    except (ValueError, Exception):
        await msg.answer(
            "❌ قیمت نامعتبر است.\n\n"
            "✅ فرمت‌های قابل قبول:\n"
            "• <code>0.005</code>\n"
            "• <code>0,005</code>\n"
            "• <code>2.50</code>\n"
            "• <code>۰.۰۰۵</code> (فارسی)",
            parse_mode="HTML"
        ); return
    await state.update_data(new_svc_price=price)
    await state.set_state(PanelAdminState.svc_min)
    await msg.answer(
        "➕ <b>خدمت جدید — مرحله ۳/۴</b>\n{'━'*28}\n\n"
        "📊 <b>حداقل تعداد قابل سفارش:</b>\n<i>مثال: 100</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.svc_min)
async def adm_svc_min(msg: Message, state: FSMContext):
    try:
        mn = int((msg.text or "").strip())
        if mn <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح مثبت وارد کنید."); return
    await state.update_data(new_svc_min=mn)
    await state.set_state(PanelAdminState.svc_max)
    await msg.answer(
        "➕ <b>خدمت جدید — مرحله ۴/۴</b>\n{'━'*28}\n\n"
        f"📊 <b>حداکثر تعداد قابل سفارش:</b>\n<i>باید بیشتر از {mn:,} باشد</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.svc_max)
async def adm_svc_max(msg: Message, state: FSMContext):
    data = await state.get_data()
    mn   = data.get("new_svc_min", 1)
    try:
        mx = int((msg.text or "").strip())
        if mx <= mn: raise ValueError
    except ValueError:
        await msg.answer(f"❌ باید بیشتر از {mn:,} باشد."); return
    await state.update_data(new_svc_max=mx)
    await state.set_state(PanelAdminState.svc_desc)
    await msg.answer(
        "➕ <b>خدمت جدید — توضیح (اختیاری)</b>\n{'━'*28}\n\n"
        "📄 <b>توضیح خدمت:</b>\n<i>برای رد کردن /skip بزنید</i>",
        reply_markup=_cancel_kb("adm_panels"),
        parse_mode="HTML"
    )

@router.message(PanelAdminState.svc_desc)
async def adm_svc_desc(msg: Message, state: FSMContext):
    desc = "" if (msg.text or "").strip() == "/skip" else (msg.text or "").strip()
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as s:
        svc = await create_service(
            s, data["new_svc_cat_id"], data["new_svc_name"],
            data["new_svc_price"], data["new_svc_min"], data["new_svc_max"], desc
        )
        await s.commit()
        sid = svc.id
        cid = data["new_svc_cat_id"]
    await msg.answer(
        f"✅ <b>خدمت ایجاد شد!</b>\n{'━'*28}\n"
        f"🆔 شناسه: <b>#{sid}</b>\n"
        f"📌 اسم: <b>{data['new_svc_name']}</b>\n"
        f"💰 قیمت: <b>${data['new_svc_price']:.2f}</b> / واحد\n"
        f"📊 حداقل: <b>{data['new_svc_min']:,}</b> | حداکثر: <b>{data['new_svc_max']:,}</b>\n"
        + (f"📄 توضیح: <i>{desc}</i>\n" if desc else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ خدمت دیگر",    callback_data=f"adm_pcat_addsvc_{cid}")],
            [InlineKeyboardButton(text="🔙 بازگشت به دسته", callback_data=f"adm_pcat_{cid}")],
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.regexp(r"^adm_psvc_\d+$"))
async def adm_psvc_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    sid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
    if not svc:
        await cb.message.edit_text("❌ خدمت یافت نشد.", reply_markup=_back("adm_panels")); return
    st = "✅ فعال" if svc.is_active else "🔴 غیرفعال"
    await cb.message.edit_text(
        f"📌 <b>{svc.name}</b>\n{'━'*28}\n"
        f"💰 قیمت: <b>${svc.price:.4f}</b> / واحد\n"
        f"📊 حداقل: <b>{svc.min_qty:,}</b> | حداکثر: <b>{svc.max_qty:,}</b>\n"
        f"📊 وضعیت: {st}\n"
        + (f"📄 توضیح: <i>{svc.description}</i>\n" if svc.description else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ ویرایش اسم",   callback_data=f"adm_psvc_editname_{sid}"),
             InlineKeyboardButton(text="💰 ویرایش قیمت",  callback_data=f"adm_psvc_editprice_{sid}")],
            [InlineKeyboardButton(text="📊 ویرایش min/max",callback_data=f"adm_psvc_editmin_{sid}"),
             InlineKeyboardButton(
                text="🔴 غیرفعال" if svc.is_active else "✅ فعال",
                callback_data=f"adm_psvc_toggle_{sid}"
            )],
            [InlineKeyboardButton(text="🗑 حذف خدمت",     callback_data=f"adm_psvc_del_{sid}")],
            [InlineKeyboardButton(text="🔙 بازگشت",        callback_data=f"adm_pcat_{svc.category_id}")],
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data.regexp(r"^adm_psvc_toggle_\d+$"))
async def adm_psvc_toggle(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    sid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
        if svc:
            await update_service(s, sid, is_active=not svc.is_active)
            await s.commit()
    await cb.answer("✅ وضعیت تغییر کرد")
    cb.data = f"adm_psvc_{sid}"
    await adm_psvc_detail(cb)

@router.callback_query(F.data.regexp(r"^adm_psvc_del_\d+$"))
async def adm_psvc_del(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    sid = int(cb.data.split("_")[-1])
    async with AsyncSessionLocal() as s:
        svc = await get_service(s, sid)
        cid = svc.category_id if svc else 0
        await delete_service(s, sid)
        await s.commit()
    await cb.answer("✅ خدمت حذف شد")
    cb.data = f"adm_pcat_{cid}"
    await adm_pcat_detail(cb)

@router.callback_query(F.data.regexp(r"^adm_psvc_editname_\d+$"))
async def adm_psvc_editname(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    sid = int(cb.data.split("_")[-1])
    await state.update_data(edit_svc_id=sid, edit_field="name")
    await state.set_state(PanelAdminState.edit_value)
    await cb.answer()
    await cb.message.edit_text("✏️ <b>اسم جدید خدمت را وارد کنید:</b>",
                               reply_markup=_cancel_kb(f"adm_psvc_{sid}"), parse_mode="HTML")

@router.callback_query(F.data.regexp(r"^adm_psvc_editprice_\d+$"))
async def adm_psvc_editprice(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    sid = int(cb.data.split("_")[-1])
    await state.update_data(edit_svc_id=sid, edit_field="price")
    await state.set_state(PanelAdminState.edit_value)
    await cb.answer()
    await cb.message.edit_text("💰 <b>قیمت جدید را وارد کنید (دلار):</b>\n<i>مثال: 0.5</i>",
                               reply_markup=_cancel_kb(f"adm_psvc_{sid}"), parse_mode="HTML")

@router.callback_query(F.data.regexp(r"^adm_psvc_editmin_\d+$"))
async def adm_psvc_editmin(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    sid = int(cb.data.split("_")[-1])
    await state.update_data(edit_svc_id=sid, edit_field="min_qty")
    await state.set_state(PanelAdminState.edit_value)
    await cb.answer()
    await cb.message.edit_text("📊 <b>حداقل تعداد جدید را وارد کنید:</b>",
                               reply_markup=_cancel_kb(f"adm_psvc_{sid}"), parse_mode="HTML")


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۶ — مدیریت سفارش‌ها از گروه (ریپلی)
# ══════════════════════════════════════════════════════════════════════════════

@router.message(F.reply_to_message & F.text.regexp(r"^[/!]?(صف|انجام|تکمیل|رد|partial)(\s+\d+)?$"))
async def group_order_reply(msg: Message, state: FSMContext, bot: Bot):
    """ریپلی روی پیام سفارش در گروه → تغییر وضعیت + edit پیام اصلی"""
    if not await _is_admin(msg.from_user.id): return
    original = msg.reply_to_message.text or msg.reply_to_message.caption or ""
    import re as _re
    m = _re.search(r"سفارش #(\d+)", original)
    if not m: return
    order_id  = int(m.group(1))
    raw_parts = (msg.text or "").strip().lstrip("/!").split()
    cmd       = raw_parts[0].lower() if raw_parts else ""
    status_map = {"صف":"pending","انجام":"processing","تکمیل":"completed","رد":"rejected"}
    if cmd == "partial":
        qty = None
        if len(raw_parts) >= 2:
            try: qty = int(raw_parts[1])
            except ValueError: pass
        if qty is None:
            await state.update_data(group_partial_order_id=order_id,
                                    group_partial_msg_id=msg.reply_to_message.message_id,
                                    group_partial_chat_id=msg.chat.id)
            await state.set_state(PanelAdminState.partial_qty)
            try:
                await msg.reply(
                    f"⚠️ <b>تکمیل جزئی — سفارش #{order_id}</b>\n\n"
                    "چند تا انجام شد؟ (عدد بفرست)\n<i>یا مستقیم: partial 500</i>",
                    parse_mode="HTML"
                )
            except Exception: pass
            return
        await _apply_group_status(msg, bot, order_id, "partial",
                                  partial_qty=qty, original_msg_id=msg.reply_to_message.message_id)
        return
    status = status_map.get(cmd)
    if not status: return
    await _apply_group_status(msg, bot, order_id, status,
                              original_msg_id=msg.reply_to_message.message_id)


async def _apply_group_status(msg: Message, bot: Bot, order_id: int, status: str,
                               partial_qty: int = None, original_msg_id: int = None):
    """اعمال وضعیت + edit پیام اصلی گروه"""
    from html import escape as _esc
    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, order_id)
        if not order:
            try: await msg.reply(f"❌ سفارش #{order_id} یافت نشد.")
            except Exception: pass
            return
        if order.status in ("completed", "rejected", "partial"):
            try: await msg.reply(f"⛔️ سفارش #{order_id} نهایی شده و قابل تغییر نیست.")
            except Exception: pass
            return
        refund = 0.0
        if status == "rejected":
            refund = await process_panel_refund(s, order, completed_qty=0)
        elif status == "partial" and partial_qty is not None:
            refund = await process_panel_refund(s, order, completed_qty=partial_qty)
        await update_panel_order_status(s, order_id, status, completed_qty=partial_qty)
        await s.commit()
        user_tg     = order.user.telegram_id if order.user else None
        svc_name    = order.service_name or ""
        quantity    = order.quantity
        link        = order.link or ""
        total_price = float(order.total_price)
        created_at  = order.created_at.strftime("%Y-%m-%d %H:%M")
        grp_msg_id  = order.group_message_id
    _ST_FA = {"pending":"در انتظار","processing":"در حال انجام",
              "completed":"تکمیل شد","partial":"تکمیل جزئی","rejected":"رد شد"}
    _ST_IC = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","rejected":"❌"}
    icon      = _ST_IC.get(status, "📌")
    status_fa = _ST_FA.get(status, status)
    if grp_msg_id and msg.chat.id:
        new_text = (
            f"🆕 <b>سفارش #{order_id}</b>\n"
            f"{'━'*28}\n"
            f"📌 خدمت: <b>{_esc(svc_name[:50])}</b>\n"
            f"🔗 لینک: <code>{_esc(link[:100])}</code>\n"
            f"🔢 تعداد: <b>{quantity:,}</b>\n"
            f"💰 مبلغ: <b>${total_price:.4f}</b>\n"
            f"📅 تاریخ: <b>{created_at}</b>\n"
            f"{'━'*28}\n"
            f"{icon} وضعیت: <b>{status_fa}</b>"
        )
        if partial_qty is not None:
            new_text += f"\n✅ انجام شده: <b>{partial_qty:,}</b>"
        if refund > 0:
            new_text += f"\n↩️ بازگشت وجه: <b>${refund:.4f}</b>"
        try:
            _panel_id_grp = order.panel_id if order else 0
            _is_final_grp = status in ("completed", "rejected", "partial")
            _kb_grp = None if _is_final_grp else InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 در انجام", callback_data=f"adm_grp_porder_{order_id}_{_panel_id_grp}_processing"),
                    InlineKeyboardButton(text="✅ تکمیل",    callback_data=f"adm_grp_porder_{order_id}_{_panel_id_grp}_completed"),
                ],
                [
                    InlineKeyboardButton(text="⚠️ جزئی",    callback_data=f"adm_grp_porder_{order_id}_{_panel_id_grp}_partial"),
                    InlineKeyboardButton(text="❌ رد",       callback_data=f"adm_grp_porder_{order_id}_{_panel_id_grp}_rejected"),
                ],
            ])
            await bot.edit_message_text(
                chat_id=msg.chat.id, message_id=grp_msg_id,
                text=new_text, parse_mode="HTML",
                reply_markup=_kb_grp
            )
        except Exception as e:
            logger.warning(f"Cannot edit group msg #{grp_msg_id}: {e}")
    try: await msg.delete()
    except Exception: pass
    if user_tg:
        await notify_order_status(bot, user_tg, order_id, svc_name, status,
                                  quantity=quantity, completed_qty=partial_qty, refund=refund)
        if refund > 0:
            from sqlalchemy import select as _sel
            from db.models import User as _User
            async with AsyncSessionLocal() as s3:
                ur  = await s3.execute(_sel(_User).where(_User.telegram_id == user_tg))
                u   = ur.scalar_one_or_none()
                bal = float(u.balance) if u else 0
            reason = "رد شدن سفارش" if status == "rejected" else "تکمیل جزئی سفارش"
            await notify_refund(bot, user_tg, refund, order_id, reason, bal)


# ══════════════════════════════════════════════════════════════════════════════
# بخش ۷ — سفارشات پنل (ادمین)
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^adm_panel_orders_\d+$"))
async def adm_panel_orders(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    pid = int(cb.data.split("_")[-1])
    from sqlalchemy import select, func
    from db.models import PanelOrder, Panel
    STATUS_ICONS = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","rejected":"❌"}
    SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    async with AsyncSessionLocal() as s:
        pr = await s.execute(select(Panel).where(Panel.id == pid))
        panel = pr.scalar_one_or_none()
        if not panel:
            await cb.message.edit_text("❌ پنل یافت نشد.", reply_markup=_back("adm_panels")); return
        st_res = await s.execute(
            select(
                func.count(PanelOrder.id).label("total"),
                func.sum(PanelOrder.total_price).label("revenue"),
                func.count(PanelOrder.id).filter(PanelOrder.status.in_(["pending","processing"])).label("active"),
                func.count(PanelOrder.id).filter(PanelOrder.status == "completed").label("completed"),
                func.count(PanelOrder.id).filter(PanelOrder.status == "partial").label("partial"),
                func.count(PanelOrder.id).filter(PanelOrder.status == "rejected").label("rejected"),
            ).where(PanelOrder.panel_id == pid)
        )
        st = st_res.one()
        res = await s.execute(
            select(PanelOrder)
            .where(PanelOrder.panel_id == pid, PanelOrder.status.in_(["pending","processing"]))
            .order_by(PanelOrder.created_at.desc()).limit(25)
        )
        orders = list(res.scalars().all())
    total     = st.total or 0
    revenue   = float(st.revenue or 0)
    active    = st.active or 0
    completed = st.completed or 0
    partial   = st.partial or 0
    rejected  = st.rejected or 0
    text = (
        "📦 <b>" + panel.button_label + "</b>\n" + SEP + "\n"
        + "📊 کل: <b>" + str(total) + "</b>  |  "
        + "⏳ فعال: <b>" + str(active) + "</b>  |  "
        + "✅ تکمیل: <b>" + str(completed) + "</b>\n"
        + ("⚠️ جزئی: <b>" + str(partial) + "</b>  |  " if partial else "")
        + "❌ رد: <b>" + str(rejected) + "</b>  |  "
        + "💰 <b>$" + f"{revenue:.4f}" + "</b>\n"
        + SEP + "\n"
        + "⏳ فعال — " + str(len(orders)) + " سفارش"
    )
    rows = []
    for o in orders:
        icon = STATUS_ICONS.get(o.status, "📌")
        svc  = (o.service_name or "")[:22]
        rows.append([InlineKeyboardButton(
            text=icon + " #" + str(o.id) + " | " + svc + " | $" + f"{o.total_price:.3f}",
            callback_data="adm_porder_" + str(o.id) + "_" + str(pid)
        )])
    if not orders:
        rows.append([InlineKeyboardButton(text="— سفارش فعالی وجود ندارد —", callback_data="noop")])
    rows.append([
        InlineKeyboardButton(text="⏳ فعال",  callback_data=f"adm_porders_f_{pid}_active"),
        InlineKeyboardButton(text="✅ تکمیل", callback_data=f"adm_porders_f_{pid}_completed"),
        InlineKeyboardButton(text="❌ رد شد", callback_data=f"adm_porders_f_{pid}_rejected"),
    ])
    rows.append([
        InlineKeyboardButton(text="⚠️ جزئی",  callback_data=f"adm_porders_f_{pid}_partial"),
        InlineKeyboardButton(text="🗒 همه",    callback_data=f"adm_porders_f_{pid}_all"),
        InlineKeyboardButton(text="🔍 سرچ",    callback_data=f"adm_porder_search_{pid}"),
    ])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data=f"adm_panel_{pid}")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^adm_porders_f_\d+_\w+$"))
async def adm_porders_filter_pa(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    parts = cb.data.split("_")
    pid, flt = int(parts[3]), parts[4]
    from sqlalchemy import select, func
    from db.models import PanelOrder, Panel
    STATUS_ICONS = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","rejected":"❌"}
    FILTER_MAP = {
        "active":    [PanelOrder.status.in_(["pending","processing"])],
        "pending":   [PanelOrder.status == "pending"],
        "processing":[PanelOrder.status == "processing"],
        "completed": [PanelOrder.status == "completed"],
        "partial":   [PanelOrder.status == "partial"],
        "rejected":  [PanelOrder.status == "rejected"],
        "all":       [],
    }
    FILTER_LABELS = {
        "active":"⏳ فعال","pending":"⏳ در صف","processing":"🔄 در انجام",
        "completed":"✅ تکمیل","partial":"⚠️ جزئی","rejected":"❌ رد شد","all":"🗒 همه"
    }
    SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    async with AsyncSessionLocal() as s:
        pr = await s.execute(select(Panel).where(Panel.id == pid))
        panel = pr.scalar_one_or_none()
        if not panel:
            await cb.message.edit_text("❌ پنل یافت نشد.", reply_markup=_back("adm_panels")); return
        st_res = await s.execute(
            select(
                func.count(PanelOrder.id).label("total"),
                func.sum(PanelOrder.total_price).label("revenue"),
                func.count(PanelOrder.id).filter(PanelOrder.status.in_(["pending","processing"])).label("active"),
                func.count(PanelOrder.id).filter(PanelOrder.status == "completed").label("completed"),
                func.count(PanelOrder.id).filter(PanelOrder.status == "partial").label("partial"),
                func.count(PanelOrder.id).filter(PanelOrder.status == "rejected").label("rejected"),
            ).where(PanelOrder.panel_id == pid)
        )
        st = st_res.one()
        extra = FILTER_MAP.get(flt, [])
        q = select(PanelOrder).where(PanelOrder.panel_id == pid)
        for f in extra: q = q.where(f)
        q = q.order_by(PanelOrder.created_at.desc()).limit(25)
        res = await s.execute(q)
        orders = list(res.scalars().all())
    total     = st.total or 0
    revenue   = float(st.revenue or 0)
    active    = st.active or 0
    completed = st.completed or 0
    partial   = st.partial or 0
    rejected  = st.rejected or 0
    cur_label = FILTER_LABELS.get(flt, flt)
    text = (
        "📦 <b>" + panel.button_label + "</b>\n" + SEP + "\n"
        + "📊 کل: <b>" + str(total) + "</b>  |  "
        + "⏳ فعال: <b>" + str(active) + "</b>  |  "
        + "✅ تکمیل: <b>" + str(completed) + "</b>\n"
        + ("⚠️ جزئی: <b>" + str(partial) + "</b>  |  " if partial else "")
        + "❌ رد: <b>" + str(rejected) + "</b>  |  "
        + "💰 <b>$" + f"{revenue:.4f}" + "</b>\n"
        + SEP + "\n"
        + "فیلتر: <b>" + cur_label + "</b>  —  " + str(len(orders)) + " سفارش"
    )
    rows = []
    for o in orders:
        icon = STATUS_ICONS.get(o.status, "📌")
        svc  = (o.service_name or "")[:22]
        rows.append([InlineKeyboardButton(
            text=icon + " #" + str(o.id) + " | " + svc + " | $" + f"{o.total_price:.3f}",
            callback_data="adm_porder_" + str(o.id) + "_" + str(pid)
        )])
    if not orders:
        rows.append([InlineKeyboardButton(text="— سفارشی در این دسته نیست —", callback_data="noop")])
    rows.append([
        InlineKeyboardButton(text="⏳ فعال",  callback_data=f"adm_porders_f_{pid}_active"),
        InlineKeyboardButton(text="✅ تکمیل", callback_data=f"adm_porders_f_{pid}_completed"),
        InlineKeyboardButton(text="❌ رد شد", callback_data=f"adm_porders_f_{pid}_rejected"),
    ])
    rows.append([
        InlineKeyboardButton(text="⚠️ جزئی",  callback_data=f"adm_porders_f_{pid}_partial"),
        InlineKeyboardButton(text="🗒 همه",    callback_data=f"adm_porders_f_{pid}_all"),
        InlineKeyboardButton(text="🔍 سرچ",    callback_data=f"adm_porder_search_{pid}"),
    ])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data=f"adm_panel_{pid}")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^adm_porder_search_\d+$"))
async def adm_porder_search_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    pid = int(cb.data.split("_")[-1])
    await state.update_data(search_panel_id=pid)
    await state.set_state(PanelOrderSearchState.query)
    await cb.answer()
    await cb.message.edit_text(
        "🔍 <b>جستجوی سفارش</b>\n{'━'*28}\n\n"
        "شناسه سفارش، یوزرنیم یا بخشی از اسم خدمت را وارد کنید:",
        reply_markup=_cancel_kb(f"adm_panel_orders_{pid}"),
        parse_mode="HTML"
    )


@router.message(PanelOrderSearchState.query)
async def adm_porder_search_handle(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid  = data.get("search_panel_id", 0)
    q    = (msg.text or "").strip()
    await state.clear()
    from sqlalchemy import select, or_
    from db.models import PanelOrder, User
    STATUS_ICONS = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","rejected":"❌"}
    async with AsyncSessionLocal() as s:
        # جستجو بر اساس ID یا اسم خدمت
        filters = [PanelOrder.panel_id == pid]
        if q.isdigit():
            filters.append(PanelOrder.id == int(q))
            res = await s.execute(select(PanelOrder).where(*filters).limit(10))
        else:
            res = await s.execute(
                select(PanelOrder)
                .where(PanelOrder.panel_id == pid,
                       PanelOrder.service_name.ilike(f"%{q}%"))
                .order_by(PanelOrder.created_at.desc()).limit(10)
            )
        orders = list(res.scalars().all())
        # جستجو بر اساس یوزرنیم
        if not orders and not q.isdigit():
            uq = q.lstrip("@")
            ur = await s.execute(select(User).where(User.username.ilike(f"%{uq}%")))
            users = list(ur.scalars().all())
            if users:
                uids = [u.id for u in users]
                or2  = await s.execute(
                    select(PanelOrder)
                    .where(PanelOrder.panel_id == pid, PanelOrder.user_id.in_(uids))
                    .order_by(PanelOrder.created_at.desc()).limit(10)
                )
                orders = list(or2.scalars().all())
    if not orders:
        await msg.answer(
            f"❌ سفارشی با «{q}» یافت نشد.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_panel_orders_{pid}")]
            ])
        ); return
    rows = []
    for o in orders:
        icon = STATUS_ICONS.get(o.status, "📌")
        rows.append([InlineKeyboardButton(
            text=f"{icon} #{o.id} — {(o.service_name or '')[:20]} — ${o.total_price:.3f}",
            callback_data=f"adm_porder_{o.id}_{pid}"
        )])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_panel_orders_{pid}")])
    await msg.answer(
        f"🔍 نتایج جستجو برای «{q}»: <b>{len(orders)}</b> مورد",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML"
    )


@router.callback_query(F.data.regexp(r"^adm_porder_\d+_\d+$"))
async def adm_porder_detail(cb: CallbackQuery):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    await cb.answer()
    parts    = cb.data.split("_")
    oid, pid = int(parts[2]), int(parts[3])
    from sqlalchemy import select
    from db.models import PanelOrder, PanelService, PanelCategory, User
    async with AsyncSessionLocal() as s:
        res   = await s.execute(select(PanelOrder).where(PanelOrder.id == oid))
        order = res.scalar_one_or_none()
        if not order:
            await cb.message.edit_text("❌ سفارش یافت نشد.", reply_markup=_back(f"adm_panel_orders_{pid}")); return
        ur   = await s.execute(select(User).where(User.id == order.user_id))
        user = ur.scalar_one_or_none()
        cat_name = ""
        svc_r = await s.execute(select(PanelService).where(PanelService.id == order.service_id))
        svc   = svc_r.scalar_one_or_none()
        if svc:
            cat_r = await s.execute(select(PanelCategory).where(PanelCategory.id == svc.category_id))
            cat   = cat_r.scalar_one_or_none()
            cat_name = (cat.icon + " " + cat.name) if cat else ""
        from services.settings_service import get_setting as _gs
        show_uid = await _gs(s, "show_user_id_in_orders", "1")
    SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    STATUS_ICONS = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","rejected":"❌"}
    STATUS_FA    = {"pending":"در انتظار","processing":"در حال انجام","completed":"تکمیل شد","partial":"تکمیل جزئی","rejected":"رد شد"}
    icon     = STATUS_ICONS.get(order.status, "📌")
    is_final = order.status in ("completed", "rejected")
    panel_nm = order.panel_name or ("پنل #" + str(order.panel_id))
    user_line = ""
    if show_uid == "1" and user:
        uname     = ("@" + user.username) if user.username else ""
        user_line = "👤 کاربر: <code>" + str(user.telegram_id) + "</code>" + (" (" + uname + ")" if uname else "") + "\n"
    svc_name  = order.service_name or "—"
    link_val  = order.link or "—"
    text = (
        "📦 <b>سفارش #" + str(order.id) + "</b>\n" + SEP + "\n"
        + "🏷 پنل: <b>" + panel_nm + "</b>\n"
        + ("📂 دسته: <b>" + cat_name + "</b>\n" if cat_name else "")
        + "📌 خدمت: <b>" + svc_name + "</b>\n"
        + SEP + "\n"
        + user_line
        + "🔗 لینک: <code>" + link_val + "</code>\n"
        + "🔢 تعداد: <b>" + f"{order.quantity:,}" + "</b>\n"
        + "💰 مبلغ: <b>$" + f"{order.total_price:.4f}" + "</b>\n"
        + ("📝 توضیح: <i>" + order.note + "</i>\n" if order.note else "")
        + SEP + "\n"
        + icon + " وضعیت: <b>" + STATUS_FA.get(order.status, order.status) + "</b>\n"
        + ("✅ انجام‌شده: <b>" + f"{order.completed_qty:,}" + "</b>\n" if order.completed_qty else "")
        + ("↩️ بازگشت وجه: <b>$" + f"{order.refund_amount:.4f}" + "</b>\n" if order.refund_amount else "")
        + ("📝 یادداشت: <i>" + order.admin_note + "</i>\n" if order.admin_note else "")
        + "⏰ زمان: <code>" + order.created_at.strftime("%Y-%m-%d %H:%M") + "</code>"
    )
    rows = []
    if not is_final:
        rows.append([
            InlineKeyboardButton(text="⏳ در صف",        callback_data=f"adm_porder_st_{oid}_{pid}_pending"),
            InlineKeyboardButton(text="🔄 در حال انجام", callback_data=f"adm_porder_st_{oid}_{pid}_processing"),
        ])
        rows.append([
            InlineKeyboardButton(text="✅ تکمیل شد",     callback_data=f"adm_porder_st_{oid}_{pid}_completed"),
            InlineKeyboardButton(text="⚠️ جزئی",         callback_data=f"adm_porder_partial_{oid}_{pid}"),
        ])
        rows.append([InlineKeyboardButton(text="❌ رد شد", callback_data=f"adm_porder_st_{oid}_{pid}_rejected")])
    else:
        rows.append([InlineKeyboardButton(text=icon + " وضعیت نهایی — تغییر ممکن نیست", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_panel_orders_{pid}")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(F.data.regexp(r"^adm_porder_st_\d+_\d+_\w+$"))
async def adm_porder_set_status(cb: CallbackQuery, bot: Bot):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    parts  = cb.data.split("_")
    oid, pid, status = int(parts[3]), int(parts[4]), parts[5]
    from sqlalchemy import select
    from db.models import PanelOrder, User
    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, oid)
        if not order: await cb.answer("❌ یافت نشد", show_alert=True); return
        if order.status in ("completed", "rejected"):
            await cb.answer("⛔️ سفارش نهایی شده و قابل تغییر نیست.", show_alert=True); return
        refund = 0.0
        if status == "rejected":
            refund = await process_panel_refund(s, order, completed_qty=0)
        await update_panel_order_status(s, oid, status)
        await s.commit()
        ur = await s.execute(select(User).where(User.id == order.user_id))
        user = ur.scalar_one_or_none()
        user_tg = user.telegram_id if user else None
        bal = float(user.balance) if user else 0
    STATUS_FA = {"pending":"در انتظار","processing":"در حال انجام",
                 "completed":"تکمیل شد","partial":"تکمیل جزئی","rejected":"رد شد"}
    await cb.answer(f"✅ وضعیت → {STATUS_FA.get(status, status)}")
    if user_tg:
        await notify_order_status(bot, user_tg, oid, order.service_name or "", status,
                                  quantity=order.quantity, refund=refund)
        if refund > 0:
            await notify_refund(bot, user_tg, refund, oid, "رد شدن سفارش", bal)
    # آپدیت پیام گروه اگه وجود داشت
    if order.group_message_id and order.panel_id:
        from sqlalchemy import select as _sel
        from db.models import Panel
        async with AsyncSessionLocal() as s2:
            pr = await s2.execute(_sel(Panel).where(Panel.id == order.panel_id))
            panel = pr.scalar_one_or_none()
        if panel and panel.group_chat_id:
            try:
                _new_grp = (
                    f"🆕 <b>سفارش #{oid}</b>\n"
                    f"{'━'*28}\n"
                    f"📌 خدمت: <b>{(order.service_name or '')[:50]}</b>\n"
                    f"🔗 لینک: <code>{(order.link or '')[:100]}</code>\n"
                    f"🔢 تعداد: <b>{order.quantity:,}</b>\n"
                    f"💰 مبلغ: <b>${float(order.total_price):.4f}</b>\n"
                    f"{'━'*28}\n"
                    f"{STATUS_ICONS.get(status,'📌')} وضعیت: <b>{STATUS_FA.get(status,status)}</b>"
                    + (f"\n↩️ بازگشت وجه: <b>${refund:.4f}</b>" if refund > 0 else "")
                )
                _is_final_cb = status in ("completed", "rejected", "partial")
                _kb_cb = None if _is_final_cb else InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🔄 در انجام", callback_data=f"adm_grp_porder_{oid}_{pid}_processing"),
                        InlineKeyboardButton(text="✅ تکمیل",    callback_data=f"adm_grp_porder_{oid}_{pid}_completed"),
                    ],
                    [
                        InlineKeyboardButton(text="⚠️ جزئی",    callback_data=f"adm_grp_porder_{oid}_{pid}_partial"),
                        InlineKeyboardButton(text="❌ رد",       callback_data=f"adm_grp_porder_{oid}_{pid}_rejected"),
                    ],
                ])
                await bot.edit_message_text(
                    chat_id=panel.group_chat_id,
                    message_id=order.group_message_id,
                    text=_new_grp, parse_mode="HTML",
                    reply_markup=_kb_cb
                )
            except Exception as _eg:
                logger.warning(f"Cannot edit group msg for order #{oid}: {_eg}")
    cb.data = f"adm_porder_{oid}_{pid}"
    await adm_porder_detail(cb)


@router.callback_query(F.data.regexp(r"^adm_porder_partial_\d+_\d+$"))
async def adm_porder_partial_start(cb: CallbackQuery, state: FSMContext):
    if not await _is_admin(cb.from_user.id): await cb.answer("⛔️", show_alert=True); return
    parts = cb.data.split("_")
    oid, pid = int(parts[3]), int(parts[4])
    await state.update_data(partial_order_id=oid, partial_panel_id=pid)
    await state.set_state(PanelAdminState.partial_qty)
    await cb.answer()
    await cb.message.edit_text(
        f"⚠️ <b>تکمیل جزئی — سفارش #{oid}</b>\n{'━'*28}\n\n"
        "چند تا انجام شد؟ (عدد وارد کنید):",
        reply_markup=_cancel_kb(f"adm_porder_{oid}_{pid}"),
        parse_mode="HTML"
    )


@router.message(PanelAdminState.partial_qty)
async def adm_porder_partial_qty(msg: Message, state: FSMContext, bot: Bot):
    try:
        qty = int((msg.text or "").strip())
        if qty < 0: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح غیرمنفی وارد کنید."); return
    data = await state.get_data()
    oid  = data.get("partial_order_id")
    pid  = data.get("partial_panel_id")
    await state.clear()
    from sqlalchemy import select
    from db.models import PanelOrder, User
    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, oid)
        if not order: await msg.answer("❌ سفارش یافت نشد."); return
        refund = await process_panel_refund(s, order, completed_qty=qty)
        await update_panel_order_status(s, oid, "partial", completed_qty=qty)
        await s.commit()
        ur = await s.execute(select(User).where(User.id == order.user_id))
        user = ur.scalar_one_or_none()
        user_tg = user.telegram_id if user else None
        bal = float(user.balance) if user else 0
    await msg.answer(
        f"✅ <b>تکمیل جزئی ثبت شد</b>\n{'━'*28}\n"
        f"سفارش: <b>#{oid}</b>\n"
        f"انجام شده: <b>{qty:,}</b>\n"
        f"↩️ بازگشت وجه: <b>${refund:.4f}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"adm_panel_orders_{pid}")]
        ]),
        parse_mode="HTML"
    )
    if user_tg:
        await notify_order_status(bot, user_tg, oid, order.service_name or "", "partial",
                                  quantity=order.quantity, completed_qty=qty, refund=refund)
        if refund > 0:
            await notify_refund(bot, user_tg, refund, oid, "تکمیل جزئی سفارش", bal)

@router.callback_query(F.data == "noop")
async def noop_handler(cb: CallbackQuery):
    await cb.answer()





# ── تغییر وضعیت سفارش از دکمه‌های inline گروه ──────────────────────────────
@router.callback_query(F.data.regexp(r"^adm_grp_porder_\d+_\d+_\w+$"))
async def adm_grp_porder_status(cb: CallbackQuery, bot: Bot, state: FSMContext):
    """callback از دکمه‌های inline پیام گروه"""
    if not await _is_admin(cb.from_user.id):
        await cb.answer("⛔️ فقط ادمین‌ها می‌توانند وضعیت را تغییر دهند.", show_alert=True); return
    parts  = cb.data.split("_")
    oid    = int(parts[3])
    pid    = int(parts[4])
    status = parts[5]
    from sqlalchemy import select
    from db.models import PanelOrder, User
    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, oid)
        if not order:
            await cb.answer("❌ سفارش یافت نشد!", show_alert=True); return
        if order.status in ("completed", "rejected", "partial"):
            await cb.answer("⛔️ این سفارش نهایی شده و قابل تغییر نیست.", show_alert=True); return
    # ── تکمیل جزئی: نیاز به عدد داره → FSM ──
    if status == "partial":
        await state.update_data(
            grp_partial_oid=oid,
            grp_partial_pid=pid,
            grp_partial_msg_id=cb.message.message_id,
            grp_partial_chat_id=cb.message.chat.id,
        )
        await state.set_state(PanelAdminState.grp_partial_qty)
        await cb.answer()
        try:
            await cb.message.reply(
                f"⚠️ <b>تکمیل جزئی — سفارش #{oid}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "چند عدد انجام شد؟ (عدد بفرست)\n"
                "<i>مثال: 500</i>",
                parse_mode="HTML"
            )
        except Exception: pass
        return
    # ── سایر وضعیت‌ها: مستقیم اعمال ──
    await _apply_grp_inline(cb, bot, oid, pid, status)


async def _apply_grp_inline(cb: CallbackQuery, bot: Bot, oid: int, pid: int, status: str,
                             partial_qty: int = None):
    """اعمال وضعیت از دکمه inline گروه + آپدیت پیام + نوتیف کاربر"""
    from sqlalchemy import select
    from db.models import PanelOrder, User
    SEP = "━" * 28
    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, oid)
        if not order: return
        refund = 0.0
        if status == "rejected":
            refund = await process_panel_refund(s, order, completed_qty=0)
        elif status == "partial" and partial_qty is not None:
            refund = await process_panel_refund(s, order, completed_qty=partial_qty)
        await update_panel_order_status(s, oid, status, completed_qty=partial_qty)
        await s.commit()
        ur = await s.execute(select(User).where(User.id == order.user_id))
        user = ur.scalar_one_or_none()
        user_tg = user.telegram_id if user else None
        bal     = float(user.balance) if user else 0
        svc_name    = order.service_name or ""
        quantity    = order.quantity
        total_price = float(order.total_price)
    STATUS_FA    = {"pending":"در انتظار","processing":"در حال انجام",
                    "completed":"تکمیل شد","partial":"تکمیل جزئی","rejected":"رد شد"}
    STATUS_ICONS = {"pending":"⏳","processing":"🔄","completed":"✅","partial":"⚠️","rejected":"❌"}
    icon      = STATUS_ICONS.get(status, "📌")
    status_fa = STATUS_FA.get(status, status)
    _is_final = status in ("completed", "rejected", "partial")
    # ── متن آپدیت پیام گروه ──
    _new_text = (
        f"🆕 <b>سفارش #{oid}</b>\n" + SEP + "\n"
        f"📌 خدمت: <b>{svc_name[:50]}</b>\n"
        f"🔢 تعداد: <b>{quantity:,}</b>\n"
        f"💰 مبلغ: <b>${total_price:.4f}</b>\n"
        + SEP + "\n"
        f"{icon} وضعیت: <b>{status_fa}</b>"
        + (f"\n✅ انجام‌شده: <b>{partial_qty:,}</b>" if partial_qty is not None else "")
        + (f"\n↩️ بازگشت وجه: <b>${refund:.4f}</b>" if refund > 0 else "")
    )
    _kb_new = None if _is_final else InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 در انجام", callback_data=f"adm_grp_porder_{oid}_{pid}_processing"),
            InlineKeyboardButton(text="✅ تکمیل",    callback_data=f"adm_grp_porder_{oid}_{pid}_completed"),
        ],
        [
            InlineKeyboardButton(text="⚠️ جزئی",    callback_data=f"adm_grp_porder_{oid}_{pid}_partial"),
            InlineKeyboardButton(text="❌ رد",       callback_data=f"adm_grp_porder_{oid}_{pid}_rejected"),
        ],
    ])
    try:
        await cb.message.edit_text(_new_text, parse_mode="HTML", reply_markup=_kb_new)
    except Exception: pass
    await cb.answer(f"✅ وضعیت → {status_fa}")
    # ── نوتیف کاربر با جزئیات کامل ──
    if user_tg:
        _notif = (
            f"📦 <b>سفارش #{oid} — {status_fa}</b>\n" + SEP + "\n"
            f"📌 خدمت: <b>{svc_name[:50]}</b>\n"
            f"🔢 تعداد سفارش: <b>{quantity:,}</b>\n"
            + (f"✅ انجام‌شده: <b>{partial_qty:,}</b>\n" if partial_qty is not None else "")
            + (f"❌ انجام‌نشده: <b>{quantity - (partial_qty or 0):,}</b>\n" if partial_qty is not None else "")
            + SEP + "\n"
            f"💰 مبلغ پرداختی: <b>${total_price:.4f}</b>\n"
            + (f"↩️ بازگشت به کیف پول: <b>${refund:.4f}</b>\n" if refund > 0 else "")
            + (f"💳 موجودی جدید: <b>${bal:.4f}</b>\n" if refund > 0 else "")
        )
        try:
            await bot.send_message(user_tg, _notif, parse_mode="HTML")
        except Exception: pass


# ── دریافت عدد تکمیل جزئی از گروه (FSM) ────────────────────────────────────
@router.message(PanelAdminState.grp_partial_qty)
async def adm_grp_partial_qty(msg: Message, state: FSMContext, bot: Bot):
    try:
        qty = int((msg.text or "").strip())
        if qty < 0: raise ValueError
    except ValueError:
        await msg.reply("❌ عدد صحیح غیرمنفی وارد کنید."); return
    data = await state.get_data()
    oid  = data.get("grp_partial_oid")
    pid  = data.get("grp_partial_pid")
    msg_id  = data.get("grp_partial_msg_id")
    chat_id = data.get("grp_partial_chat_id")
    await state.clear()
    # ساخت یک CallbackQuery مصنوعی نداریم — مستقیم apply می‌کنیم
    from aiogram.types import Chat, Message as AioMsg
    from db.models import PanelOrder, User
    from sqlalchemy import select
    SEP = "━" * 28
    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, oid)
        if not order: await msg.reply("❌ سفارش یافت نشد."); return
        refund = await process_panel_refund(s, order, completed_qty=qty)
        await update_panel_order_status(s, oid, "partial", completed_qty=qty)
        await s.commit()
        ur = await s.execute(select(User).where(User.id == order.user_id))
        user = ur.scalar_one_or_none()
        user_tg = user.telegram_id if user else None
        bal     = float(user.balance) if user else 0
        svc_name    = order.service_name or ""
        quantity    = order.quantity
        total_price = float(order.total_price)
    # آپدیت پیام گروه
    _new_text = (
        f"🆕 <b>سفارش #{oid}</b>\n" + SEP + "\n"
        f"📌 خدمت: <b>{svc_name[:50]}</b>\n"
        f"🔢 تعداد: <b>{quantity:,}</b>\n"
        f"💰 مبلغ: <b>${total_price:.4f}</b>\n"
        + SEP + "\n"
        f"⚠️ وضعیت: <b>تکمیل جزئی</b>\n"
        f"✅ انجام‌شده: <b>{qty:,}</b>\n"
        + (f"↩️ بازگشت وجه: <b>${refund:.4f}</b>" if refund > 0 else "")
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=_new_text, parse_mode="HTML", reply_markup=None
        )
    except Exception: pass
    try: await msg.delete()
    except Exception: pass
    await msg.answer(
        f"✅ <b>تکمیل جزئی ثبت شد — سفارش #{oid}</b>\n"
        f"انجام‌شده: <b>{qty:,}</b> از <b>{quantity:,}</b>\n"
        + (f"↩️ بازگشت وجه: <b>${refund:.4f}</b>" if refund > 0 else ""),
        parse_mode="HTML"
    )
    # نوتیف کاربر با جزئیات کامل
    if user_tg:
        _notif = (
            f"📦 <b>سفارش #{oid} — تکمیل جزئی ⚠️</b>\n" + SEP + "\n"
            f"📌 خدمت: <b>{svc_name[:50]}</b>\n"
            f"🔢 تعداد سفارش: <b>{quantity:,}</b>\n"
            f"✅ انجام‌شده: <b>{qty:,}</b>\n"
            f"❌ انجام‌نشده: <b>{quantity - qty:,}</b>\n"
            + SEP + "\n"
            f"💰 مبلغ پرداختی: <b>${total_price:.4f}</b>\n"
            + (f"↩️ بازگشت به کیف پول: <b>${refund:.4f}</b>\n" if refund > 0 else "")
            + (f"💳 موجودی جدید: <b>${bal:.4f}</b>" if refund > 0 else "")
        )
        try:
            await bot.send_message(user_tg, _notif, parse_mode="HTML")
        except Exception: pass

