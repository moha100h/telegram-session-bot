import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from redis.asyncio import Redis
from services.session_manager import (
    get_all_sessions, get_active_sessions,
    add_session, delete_session, get_session_names
)

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


class AddSessionStates(StatesGroup):
    phone          = State()
    code           = State()
    password       = State()


_pending: dict = {}  # phone_code_hash per user


def sessions_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن سشن", callback_data="session_add")],
        [InlineKeyboardButton(text="📋 لیست سشن‌ها", callback_data="session_list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_sessions")
async def sessions_menu(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    await state.clear()
    sessions = await get_all_sessions()
    active   = sum(1 for s in sessions if s["active"])
    await cb.message.edit_text(
        f"📱 <b>مدیریت سشن‌ها</b>\n\n"
        f"• کل: <b>{len(sessions)}</b>\n"
        f"• فعال: <b>{active}</b>",
        parse_mode="HTML",
        reply_markup=sessions_menu_kb()
    )


@router.callback_query(F.data == "session_list")
async def session_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
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
        icon = "✅" if s["active"] else "🔴"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {s['phone']}",
            callback_data=f"session_info_{s['name']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")])
    await cb.message.edit_text(
        f"📱 <b>سشن‌ها ({len(sessions)} عدد)</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("session_info_"))
async def session_info(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    name = cb.data.replace("session_info_", "")
    from services.session_manager import get_session
    s = await get_session(name)
    if not s:
        await cb.answer("سشن یافت نشد", show_alert=True)
        return
    status = "✅ فعال" if s["active"] else "🔴 غیرفعال"
    await cb.message.edit_text(
        f"📱 <b>سشن: {s['phone']}</b>\n\n"
        f"• وضعیت: {status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 حذف", callback_data=f"session_del_{name}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="session_list")],
        ])
    )


@router.callback_query(F.data.startswith("session_del_"))
async def session_del(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    name = cb.data.replace("session_del_", "")
    await delete_session(name)
    await cb.answer("✅ سشن حذف شد")
    await session_list(cb)


# ── Add session flow ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "session_add")
async def session_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    await state.set_state(AddSessionStates.phone)
    await cb.message.edit_text(
        "📱 <b>افزودن سشن</b>\n\n"
        "شماره تلگرام را بفرستید:\n"
        "مثال: <code>+989123456789</code>\n"
        "کد تایید به شماره ارسال می‌شود",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="menu_sessions")]
        ])
    )


@router.message(AddSessionStates.phone)
async def session_add_phone(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id):
        return
    phone = message.text.strip()
    await message.answer("⏳ در حال ارسال کد...")
    result = await add_session(redis, phone, step="send_code")
    if not result["ok"]:
        await message.answer(f"❌ خطا: {result.get('error', 'unknown')}")
        await state.clear()
        return
    await state.update_data(phone=phone, phone_code_hash=result["phone_code_hash"])
    await state.set_state(AddSessionStates.code)
    await message.answer(
        "✅ کد ارسال شد\n\n"
        "کد دریافتی را وارد کنید:\n"
        "(فقط ارقام بدون فاصله)"
    )


@router.message(AddSessionStates.code)
async def session_add_code(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id):
        return
    code = message.text.strip()
    data = await state.get_data()
    result = await add_session(
        redis, data["phone"], step="sign_in",
        code=code, phone_code_hash=data["phone_code_hash"]
    )
    if result.get("need_password"):
        await state.set_state(AddSessionStates.password)
        await message.answer("🔐 رمز دو مرحلهایی (2FA) را وارد کنید:")
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
    if not is_admin(message.from_user.id):
        return
    password = message.text.strip()
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="2fa", password=password)
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
