import os
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from redis.asyncio import Redis
from services.session_manager import get_session_names, add_session

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class VirtualNumStates(StatesGroup):
    phone          = State()
    code           = State()
    password       = State()


def is_admin(uid): return uid == ADMIN_ID


@router.callback_query(F.data == "menu_virtual")
async def virtual_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    names = await get_session_names()
    await cb.message.edit_text(
        "📞 <b>شماره مجازی / لاگین سشن</b>\n\n"
        f"• سشن موجود: <b>{len(names)}</b>\n\n"
        "از طریق این بخش می‌توانید با شماره مجازی سشن اضافه کنید.\n"
        "شماره را وارد کنید کد تایید به آن ارسال می‌شود.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن سشن با شماره مجازی", callback_data="virtual_add")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )


@router.callback_query(F.data == "virtual_add")
async def virtual_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    await state.set_state(VirtualNumStates.phone)
    await cb.message.edit_text(
        "📱 <b>شماره تلگرام را بفرستید:</b>\n"
        "مثال: <code>+989123456789</code>\n"
        "کد تایید به شماره ارسال می‌شود",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="menu_virtual")]
        ])
    )


@router.message(VirtualNumStates.phone)
async def virtual_phone(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    phone = message.text.strip()
    await message.answer("⏳ در حال ارسال کد...")
    result = await add_session(redis, phone, step="send_code")
    if not result.get("ok"):
        await message.answer(f"❌ خطا: {result.get('error')}")
        await state.clear()
        return
    await state.update_data(phone=phone, phone_code_hash=result["phone_code_hash"])
    await state.set_state(VirtualNumStates.code)
    await message.answer(
        "✅ کد ارسال شد\n"
        "🔢 کد دریافتی را وارد کنید:\n"
        "(فقط ارقام بدون فاصله)"
    )


@router.message(VirtualNumStates.code)
async def virtual_code(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    code = message.text.strip()
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="sign_in",
                               code=code, phone_code_hash=data.get("phone_code_hash"))
    if result.get("need_password"):
        await state.set_state(VirtualNumStates.password)
        await message.answer("🔐 رمز دومرحلهایی (2FA) را وارد کنید:")
        return
    if not result["ok"]:
        await message.answer(f"❌ خطا: {result.get('error')}")
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


@router.message(VirtualNumStates.password)
async def virtual_password(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="2fa", password=message.text.strip())
    if not result["ok"]:
        await message.answer(f"❌ خطا: {result.get('error')}")
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
