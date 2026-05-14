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


class AddSessionStates(StatesGroup):
    phone    = State()
    code     = State()
    password = State()


class LeaveStates(StatesGroup):
    channel  = State()
    sessions = State()


def is_admin(uid): return uid == ADMIN_ID


def sessions_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن سشن",       callback_data="session_add")],
        [InlineKeyboardButton(text="📋 لیست سشن‌ها",     callback_data="session_list")],
        [InlineKeyboardButton(text="✅ تست همه سشن‌ها",  callback_data="session_verify_all")],
        [InlineKeyboardButton(text="🚪 خروج از کانال/گروه", callback_data="session_leave")],
        [InlineKeyboardButton(text="🔙 بازگشت",          callback_data="menu_main")],
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
            icon = "✅"
        elif s.get("active"):
            icon = "⚠️"
        else:
            icon = "🔴"
        name = s.get("fullname") or s.get("phone", s["name"])
        uname = f" @{s['username']}" if s.get("username") else ""
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {name}{uname}",
            callback_data=f"session_info_{s['name']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")])
    await cb.message.edit_text(
        f"📱 <b>سشن‌ها ({len(sessions)} عدد)</b>\n"
        f"✅=تستشده  ⚠️=تستنشده  🔴=فایل ندارد",
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
    icon = "✅" if s.get("verified") else ("⚠️" if s.get("active") else "🔴")
    lines = [
        f"{icon} <b>{s.get('fullname') or s.get('phone')}</b>",
        f"• شماره: <code>{s.get('phone')}</code>",
    ]
    if s.get("username"):
        lines.append(f"• یوزرنیم: @{s['username']}")
    if s.get("user_id"):
        lines.append(f"• ID: <code>{s['user_id']}</code>")
    lines.append(f"• فایل: {'\u2705' if s.get('active') else '\u274c'}")
    lines.append(f"• تست: {'\u2705 معتبر' if s.get('verified') else '\u26a0\ufe0f تست نشده'}")
    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 تست سشن", callback_data=f"session_verify_{name}")],
            [InlineKeyboardButton(text="🗑 حذف سشن", callback_data=f"session_del_{name}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="session_list")],
        ])
    )


@router.callback_query(F.data.startswith("session_verify_"))
async def session_verify_one(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_verify_", "")
    await cb.message.edit_text("⏳ در حال تست سشن...")
    result = await verify_session(name)
    if result["ok"]:
        me = result["me"]
        await cb.message.edit_text(
            f"✅ <b>سشن معتبر است</b>\n\n"
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
            f"❌ <b>سشن نامعتبر</b>\nخطا: {result.get('error')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 حذف", callback_data=f"session_del_{name}")],
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
    results = await verify_all_sessions()
    ok_count   = len(results["ok"])
    fail_count = len(results["fail"])
    fail_text  = ""
    if results["fail"]:
        fail_text = "\n\n❌ نامعتبر:\n" + "\n".join(
            f"• {f['name']}: {f['error']}" for f in results["fail"]
        )
    await cb.message.edit_text(
        f"🔍 <b>نتیجه تست سشن‌ها</b>\n\n"
        f"✅ معتبر: <b>{ok_count}</b>\n"
        f"❌ نامعتبر: <b>{fail_count}</b>"
        + fail_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 لیست سشن‌ها", callback_data="session_list")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")],
        ])
    )


@router.callback_query(F.data.startswith("session_del_"))
async def session_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_del_", "")
    await delete_session(name)
    await cb.answer("✅ سشن حذف شد")
    await session_list(cb)


# ── Leave channel flow ─────────────────────────────────────────────────────────
@router.callback_query(F.data == "session_leave")
async def leave_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    await state.set_state(LeaveStates.channel)
    await cb.message.edit_text(
        "🚪 <b>خروج از کانال/گروه</b>\n\n"
        "لینک یا یوزرنیم کانال/گروه را بفرستید:\n"
        "مثال: <code>@mychannel</code> یا <code>https://t.me/mychannel</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="menu_sessions")]
        ])
    )


@router.message(LeaveStates.channel)
async def leave_channel_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    channel = message.text.strip()
    await state.update_data(channel=channel)
    await state.set_state(LeaveStates.sessions)
    names = await get_session_names()
    await message.answer(
        f"📱 <b>انتخاب سشن‌ها</b>\n\n"
        f"تعداد سشن موجود: <b>{len(names)}</b>\n"
        f"عدد سشن برای خروج (0=همه):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="همه سشن‌ها", callback_data="leave_all")]
        ])
    )


@router.callback_query(F.data == "leave_all", LeaveStates.sessions)
async def leave_all_sessions(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    data = await state.get_data()
    await state.clear()
    await _do_leave(cb.message, data["channel"], None)


@router.message(LeaveStates.sessions)
async def leave_sessions_count(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        n = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    data = await state.get_data()
    await state.clear()
    await _do_leave(message, data["channel"], n if n > 0 else None)


async def _do_leave(msg_or_cb, channel: str, limit):
    names = await get_session_names()
    if limit:
        names = names[:limit]
    await msg_or_cb.answer(f"⏳ در حال خروج {len(names)} سشن از {channel}...")
    ok_count = 0
    fail_count = 0
    for name in names:
        r = await leave_channel(name, channel)
        if r["ok"]:
            ok_count += 1
        else:
            fail_count += 1
        await asyncio.sleep(0.5)
    await msg_or_cb.answer(
        f"🚪 <b>نتیجه خروج</b>\n\n"
        f"✅ موفق: <b>{ok_count}</b>\n"
        f"❌ ناموفق: <b>{fail_count}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")]
        ])
    )


import asyncio


# ── Add session flow ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "session_add")
async def session_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    await state.set_state(AddSessionStates.phone)
    await cb.message.edit_text(
        "➕ <b>افزودن سشن جدید</b>\n\n"
        "📱 شماره تلگرام را بفرستید:\n"
        "مثال: <code>+989123456789</code>\n"
        "کد تایید به شماره ارسال می‌شود",
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
        "✅ کد ارسال شد ☑️\n"
        "🔢 کد دریافتی را وارد کنید:\n"
        "(فقط ارقام بدون فاصله)"
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
        await message.answer("🔐 رمز دومرحلهایی (2FA) را وارد کنید:")
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
