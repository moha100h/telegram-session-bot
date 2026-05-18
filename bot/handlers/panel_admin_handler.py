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

    if field == "group_chat_id":
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
    await msg.answer(
        "✅ <b>تغییرات ذخیره شد.</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل",
             callback_data=f"adm_panel_{pid or ''}")],
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
        price = float((msg.text or "").strip().replace(",", ""))
        if price <= 0: raise ValueError
    except ValueError:
        await msg.answer("❌ قیمت باید عدد مثبت باشد. مثال: 0.5"); return
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

@router.message(F.reply_to_message & F.text.regexp(r"^[/!]?(صف|انجام|تکمیل|رد|partial)"))
async def group_order_reply(msg: Message, bot: Bot):
    """ریپلی روی پیام سفارش در گروه → تغییر وضعیت"""
    if not await _is_admin(msg.from_user.id): return
    # پیدا کردن order_id از متن پیام اصلی
    original = msg.reply_to_message.text or ""
    import re
    m = re.search(r"سفارش #(\d+)", original)
    if not m: return
    order_id = int(m.group(1))

    cmd = (msg.text or "").strip().lstrip("/!").lower()
    status_map = {
        "صف": "pending", "انجام": "processing",
        "تکمیل": "completed", "رد": "rejected",
    }

    if cmd == "partial":
        # partial — منتظر تعداد
        await msg.reply(
            "⚠️ <b>تکمیل جزئی</b>\n\n"
            f"سفارش #{order_id}\n"
            "چند تا انجام شد؟ (عدد بفرست)",
            parse_mode="HTML"
        )
        # ذخیره در یه dict موقت — برای سادگی از caption استفاده می‌کنیم
        return

    status = status_map.get(cmd)
    if not status: return

    async with AsyncSessionLocal() as s:
        order = await get_panel_order(s, order_id)
        if not order:
            await msg.reply(f"❌ سفارش #{order_id} یافت نشد."); return
        old_status = order.status
        await update_panel_order_status(s, order_id, status)

        refund = 0.0
        if status == "rejected":
            refund = await process_panel_refund(s, order, completed_qty=0)
        await s.commit()

        user_tg = order.user.telegram_id if order.user else None

    icon, status_fa = STATUS_ICONS.get(status, ("📌", status)), ""
    status_fa = {"pending":"در انتظار","processing":"در حال انجام",
                 "completed":"تکمیل شد","rejected":"رد شد"}.get(status, status)

    await msg.reply(
        f"✅ وضعیت سفارش #{order_id} به <b>{status_fa}</b> تغییر کرد."
        + (f"\n↩️ بازگشت وجه: <b>${refund:.4f}</b>" if refund > 0 else ""),
        parse_mode="HTML"
    )

    if user_tg:
        await notify_order_status(
            bot, user_tg, order_id, order.service_name or "", status,
            quantity=order.quantity, refund=refund
        )
        if refund > 0:
            async with AsyncSessionLocal() as s2:
                from sqlalchemy import select
                from db.models import User
                ur = await s2.execute(select(User).where(User.id == order.user_id))
                u  = ur.scalar_one_or_none()
                bal = float(u.balance) if u else 0
            await notify_refund(bot, user_tg, refund, order_id, "رد شدن سفارش", bal)
