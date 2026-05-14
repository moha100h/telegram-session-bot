from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from middlewares.admin import AdminMiddleware
from services.session_manager import (
    get_all_sessions, get_active_sessions,
    add_session, delete_session, get_session
)
from redis.asyncio import Redis
import os

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())


class AddSessionStates(StatesGroup):
    phone    = State()
    code     = State()
    password = State()


def sessions_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزودن سشن", callback_data="session_add")],
        [InlineKeyboardButton(text="📋 لیست سشن‌ها", callback_data="session_list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])


def back_kb(cb="menu_sessions") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]
    ])


@router.callback_query(F.data == "menu_sessions")
async def sessions_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    sessions = await get_all_sessions()
    active   = sum(1 for s in sessions if s.get("active"))
    await cb.message.edit_text(
        f"📱 <b>مدیریت سشن‌ها</b>\n\n"
        f"🟢 فعال: <b>{active}</b>\n"
        f"🟡 کل: <b>{len(sessions)}</b>",
        reply_markup=sessions_menu_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "session_list")
async def session_list(cb: CallbackQuery):
    sessions = await get_all_sessions()
    if not sessions:
        await cb.message.edit_text(
            "📭 هیچ سشنی وجود ندارد",
            reply_markup=back_kb()
        )
        return

    buttons = []
    for s in sessions:
        icon   = "🟢" if s.get("active") else "🔴"
        phone  = s.get("phone", s["name"])
        status = "فعال" if s.get("active") else "غیرفعال"
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {phone} | {status}",
                callback_data=f"session_info_{s['name']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_sessions")])
    await cb.message.edit_text(
        f"📱 <b>لیست سشن‌ها ({len(sessions)} عدد)</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("session_info_"))
async def session_info(cb: CallbackQuery):
    name    = cb.data.replace("session_info_", "")
    session = await get_session(name)
    if not session:
        await cb.answer("سشن یافت نشد", show_alert=True)
        return
    icon   = "🟢" if session.get("active") else "🔴"
    phone  = session.get("phone", name)
    status = "فعال" if session.get("active") else "غیرفعال"
    await cb.message.edit_text(
        f"{icon} <b>سشن: {phone}</b>\n"
        f"• وضعیت: {status}\n"
        f"• نام فایل: <code>{name}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 حذف سشن", callback_data=f"session_del_{name}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="session_list")],
        ])
    )


@router.callback_query(F.data.startswith("session_del_"))
async def session_delete(cb: CallbackQuery):
    name = cb.data.replace("session_del_", "")
    await delete_session(name)
    await cb.answer("✅ سشن حذف شد")
    await session_list(cb)


# ── Add session flow ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "session_add")
async def session_add_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "➕ <b>افزودن سشن جدید</b>\n\n"
        "📱 شماره تلفن را بفرستید:\n"
        "مثال: <code>+989123456789</code>",
        parse_mode="HTML",
        reply_markup=back_kb()
    )
    await state.set_state(AddSessionStates.phone)


@router.message(AddSessionStates.phone)
async def session_add_phone(message: Message, state: FSMContext, redis: Redis):
    phone = message.text.strip()
    await state.update_data(phone=phone)
    result = await add_session(redis, phone, step="send_code")
    if not result.get("ok"):
        await message.answer(
            f"❌ خطا: {result.get('error', 'unknown')}",
            reply_markup=back_kb()
        )
        await state.clear()
        return
    await state.update_data(phone_code_hash=result.get("phone_code_hash"))
    await message.answer(
        "✅ کد ارسال شد\n"
        "🔢 کد دریافتی را وارد کنید:\n"
        "(فقط ارقام بدون فاصله)",
        reply_markup=back_kb()
    )
    await state.set_state(AddSessionStates.code)


@router.message(AddSessionStates.code)
async def session_add_code(message: Message, state: FSMContext, redis: Redis):
    code = message.text.strip()
    data = await state.get_data()
    result = await add_session(
        redis, data["phone"],
        step="sign_in",
        code=code,
        phone_code_hash=data.get("phone_code_hash")
    )
    if result.get("need_password"):
        await state.set_state(AddSessionStates.password)
        await message.answer(
            "🔐 رمز دو مرحلهایی را وارد کنید:",
            reply_markup=back_kb()
        )
        return
    if not result.get("ok"):
        await message.answer(
            f"❌ خطا: {result.get('error', 'unknown')}",
            reply_markup=back_kb()
        )
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ سشن <b>{data['phone']}</b> با موفقیت اضافه شد!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 لیست سشن‌ها", callback_data="session_list")],
            [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="menu_main")],
        ])
    )


@router.message(AddSessionStates.password)
async def session_add_password(message: Message, state: FSMContext, redis: Redis):
    password = message.text.strip()
    data = await state.get_data()
    result = await add_session(
        redis, data["phone"],
        step="2fa",
        password=password
    )
    if not result.get("ok"):
        await message.answer(
            f"❌ خطا: {result.get('error', 'unknown')}",
            reply_markup=back_kb()
        )
        await state.clear()
        return
    await state.clear()
    await message.answer(
        f"✅ سشن <b>{data['phone']}</b> با موفقیت اضافه شد!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 لیست سشن‌ها", callback_data="session_list")],
            [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="menu_main")],
        ])
    )
