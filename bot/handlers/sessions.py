import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from redis.asyncio import Redis
from services.session_manager import (
    get_all_sessions, get_active_sessions,
    add_session, delete_session, get_session,
    verify_session, verify_all_sessions,
    leave_channel, get_session_names
)

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

ICON_OK   = "✅"
ICON_WARN = "⚠️"
ICON_RED  = "🔴"
ICON_NO   = "❌"


class AddSessionStates(StatesGroup):
    phone    = State()
    code     = State()
    password = State()


def is_admin(uid): return uid == ADMIN_ID


def sessions_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن سشن",           callback_data="session_add")],
        [InlineKeyboardButton(text="📋 لیست سشن‌ها",       callback_data="session_list")],
        [InlineKeyboardButton(text="✅ تست همه سشن‌ها",   callback_data="session_verify_all")],
        [InlineKeyboardButton(text="🔙 بازگشت",            callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_sessions")
async def sessions_menu(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    sessions = await get_all_sessions()
    active   = sum(1 for s in sessions if s.get("active"))
    verified = sum(1 for s in sessions if s.get("verified"))
    await cb.message.edit_text(
        f"📱 <b>مدیریت سشن‌ها</b>\n\n"
        f"• کل: <b>{len(sessions)}</b>\n"
        f"• فایل موجود: <b>{active}</b>\n"
        f"• تست شده: <b>{verified}</b>",
        reply_markup=sessions_menu_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "session_list")
async def session_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    sessions = await get_all_sessions()
    if not sessions:
        await cb.message.edit_text(
            "📭 هیچ سشنی وجود ندارد",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ افزودن", callback_data="session_add")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")],
            ])
        )
        return
    buttons = []
    for s in sessions:
        if s.get("verified"):
            icon = ICON_OK
        elif s.get("active"):
            icon = ICON_WARN
        else:
            icon = ICON_RED
        name  = s.get("fullname") or s.get("phone", s["name"])
        uname = (" @" + s["username"]) if s.get("username") else ""
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {name}{uname}",
            callback_data=f"session_info_{s['name']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")])
    await cb.message.edit_text(
        f"📱 <b>سشن‌ها ({len(sessions)} عدد)</b>\n"
        f"{ICON_OK}=تستشده  {ICON_WARN}=تستنشده  {ICON_RED}=فایل ندارد",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("session_info_"))
async def session_info(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_info_", "")
    s = await get_session(name)
    if not s:
        await cb.answer("سشن یافت نشد", show_alert=True)
        return
    icon      = ICON_OK   if s.get("verified") else (ICON_WARN if s.get("active") else ICON_RED)
    file_icon = ICON_OK   if s.get("active")   else ICON_NO
    test_icon = ICON_OK   if s.get("verified") else ICON_WARN
    test_lbl  = "معتبر" if s.get("verified") else "تست نشده"
    lines = [f"{icon} <b>{s.get('fullname') or s.get('phone', name)}</b>"]
    lines.append(f"• شماره: <code>{s.get('phone', '')}</code>")
    if s.get("username"):
        lines.append(f"• یوزرنیم: @{s['username']}")
    if s.get("user_id"):
        lines.append(f"• ID: <code>{s['user_id']}</code>")
    lines.append(f"• فایل: {file_icon}")
    lines.append(f"• تست: {test_icon} {test_lbl}")
    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 تست سشن",  callback_data=f"session_verify_{name}")],
            [InlineKeyboardButton(text="🗑 حذف سشن",  callback_data=f"session_del_{name}")],
            [InlineKeyboardButton(text="🔙 بازگشت",     callback_data="session_list")],
        ])
    )


@router.callback_query(F.data.startswith("session_verify_") & ~F.data.startswith("session_verify_all"))
async def session_verify_one(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_verify_", "")
    if name == "all": return
    await cb.message.edit_text("⏳ در حال تست سشن...")
    result = await verify_session(name)
    if result["ok"]:
        me = result["me"]
        await cb.message.edit_text(
            f"{ICON_OK} <b>سشن معتبر است</b>\n\n"
            f"• نام: {me['fullname']}\n"
            f"• شماره: <code>{me['phone']}</code>\n"
            f"• یوزرنیم: @{me['username'] or '-'}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"session_info_{name}")]
            ])
        )
    else:
        await cb.message.edit_text(
            f"{ICON_NO} <b>سشن نامعتبر</b>\nخطا: {result.get('error', '')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 حذف",      callback_data=f"session_del_{name}")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="session_list")],
            ])
        )


@router.callback_query(F.data == "session_verify_all")
async def session_verify_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    names = await get_session_names()
    if not names:
        await cb.answer("هیچ سشنی وجود ندارد", show_alert=True)
        return
    await cb.message.edit_text(f"⏳ در حال تست {len(names)} سشن...")
    results    = await verify_all_sessions()
    ok_count   = len(results["ok"])
    fail_count = len(results["fail"])
    text = (
        f"🔍 <b>نتیجه تست سشن‌ها</b>\n\n"
        f"{ICON_OK} معتبر: <b>{ok_count}</b>\n"
        f"{ICON_NO} نامعتبر: <b>{fail_count}</b>"
    )
    if results["fail"]:
        fail_lines = [f"{ICON_NO} {f['name']}: {f['error']}" for f in results["fail"]]
        text += "\n\n" + "\n".join(fail_lines)
    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 لیست سشن‌ها", callback_data="session_list")],
            [InlineKeyboardButton(text="🔙 بازگشت",     callback_data="menu_sessions")],
        ])
    )


@router.callback_query(F.data.startswith("session_del_"))
async def session_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_del_", "")
    await delete_session(name)
    await cb.answer("✅ سشن حذف شد")
    await session_list(cb)


@router.callback_query(F.data.startswith("sc_retest_"))
async def sc_retest(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("sc_retest_", "")
    await cb.message.answer(f"⏳ در حال تست سشن {name}...")
    result = await verify_session(name)
    if result["ok"]:
        me = result["me"]
        await cb.message.answer(
            f"{ICON_OK} <b>سشن معتبر شد</b>\n"
            f"• نام: {me['fullname']}\n"
            f"• شماره: <code>{me['phone']}</code>",
            parse_mode="HTML"
        )
    else:
        await cb.message.answer(
            f"{ICON_NO} سشن هنوز نامعتبر: {result.get('error')}",
            parse_mode="HTML"
        )
    await cb.answer()


@router.callback_query(F.data.startswith("sc_delete_"))
async def sc_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("sc_delete_", "")
    await delete_session(name)
    await cb.answer("✅ سشن حذف شد", show_alert=True)
    await cb.message.answer(f"🗑 سشن <code>{name}</code> حذف شد.", parse_mode="HTML")


@router.callback_query(F.data == "session_add")
async def session_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    await state.set_state(AddSessionStates.phone)
    await cb.message.edit_text(
        "➕ <b>افزودن سشن جدید</b>\n\n"
        "📱 شماره تلگرام را بفرستید:\n"
        "مثال: <code>+989123456789</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="menu_sessions")]
        ])
    )


@router.message(AddSessionStates.phone)
async def session_add_phone(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    phone = message.text.strip()
    await message.answer("⏳ در حال ارسال کد...")
    result = await add_session(redis, phone, step="send_code")
    if not result.get("ok"):
        await message.answer(f"❌ خطا: {result.get('error', 'unknown')}")
        await state.clear()
        return
    await state.update_data(phone=phone, phone_code_hash=result["phone_code_hash"])
    await state.set_state(AddSessionStates.code)
    await message.answer(
        "✅ کد ارسال شد\n"
        "🔢 کد دریافتی را وارد کنید (فقط ارقام):"
    )


@router.message(AddSessionStates.code)
async def session_add_code(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    code = message.text.strip()
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="sign_in",
                               code=code, phone_code_hash=data.get("phone_code_hash"))
    if result.get("need_password"):
        await state.set_state(AddSessionStates.password)
        await message.answer("🔐 رمز 2FA را وارد کنید:")
        return
    if not result["ok"]:
        await message.answer(f"❌ خطا: {result.get('error', 'unknown')}")
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "✅ <b>سشن با موفقیت اضافه شد!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 لیست سشن‌ها", callback_data="session_list")]
        ])
    )


@router.message(AddSessionStates.password)
async def session_add_password(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="2fa", password=message.text.strip())
    if not result["ok"]:
        await message.answer(f"❌ خطا: {result.get('error', 'unknown')}")
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "✅ <b>سشن با موفقیت اضافه شد!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 لیست سشن‌ها", callback_data="session_list")]
        ])
    )
