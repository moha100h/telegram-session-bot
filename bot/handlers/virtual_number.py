from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from middlewares.admin import AdminMiddleware
from services.session_manager import get_client, update_session_meta, auto_setup_profile
from config import SESSIONS_DIR
import os

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

class VNStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()

@router.callback_query(F.data == "menu_vnumber")
async def vn_menu(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text(
        "📲 <b>شماره مجازی</b>\n\nشماره تلگرام را بفرستید:\nمثال: <code>+989123456789</code>\n\nکد تایید به شماره ارسال می‌شود",
        parse_mode="HTML")
    await state.set_state(VNStates.waiting_phone)

@router.message(VNStates.waiting_phone)
async def vn_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    session_name = phone.replace("+", "").replace(" ", "")
    await state.update_data(session_name=session_name)
    msg = await message.answer(f"📞 ارسال کد به {phone}...")
    try:
        client = await get_client(session_name)
        await client.connect()
        result = await client.send_code_request(phone)
        await state.update_data(phone_code_hash=result.phone_code_hash)
        await msg.edit_text(
            f"✅ کد ارسال شد\n🔢 کد دریافتی را وارد کنید:\n(فقط ارقام بدون فاصله)")
        await state.update_data(client_connected=True)
        await state.set_state(VNStates.waiting_code)
    except Exception as e:
        await msg.edit_text(f"❌ خطا: {e}")
        await state.clear()

@router.message(VNStates.waiting_code)
async def vn_code(message: Message, state: FSMContext):
    code = message.text.strip().replace(" ", "").replace("-", "")
    data = await state.get_data()
    phone = data["phone"]
    session_name = data["session_name"]
    phone_code_hash = data["phone_code_hash"]
    try:
        client = await get_client(session_name)
        await client.connect()
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        me = await client.get_me()
        await client.disconnect()
        await update_session_meta(session_name, {
            "status": "active", "phone": phone,
            "first_name": me.first_name, "username": me.username, "tg_id": me.id
        })
        await state.clear()
        await message.answer(
            f"✅ سشن ذخیره شد\n👤 {me.first_name} | @{me.username or 'ندارد'}\n📞 {phone}\n\n🤖 پروفایل خودکار تنظیم می‌شود...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")]
            ]))
        await auto_setup_profile(session_name)
    except Exception as e:
        if "password" in str(e).lower() or "2fa" in str(e).lower():
            await message.answer("🔐 این حساب رمز دو مرحلهایی دارد. رمز عبور را وارد کنید:")
            await state.set_state(VNStates.waiting_password)
        else:
            await message.answer(f"❌ خطا: {e}")
            await state.clear()

@router.message(VNStates.waiting_password)
async def vn_password(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    phone = data["phone"]
    session_name = data["session_name"]
    try:
        client = await get_client(session_name)
        await client.connect()
        await client.sign_in(password=password)
        me = await client.get_me()
        await client.disconnect()
        await update_session_meta(session_name, {
            "status": "active", "phone": phone,
            "first_name": me.first_name, "username": me.username, "tg_id": me.id
        })
        await state.clear()
        await message.answer(
            f"✅ ورود موفق با رمز دو مرحلهایی\n👤 {me.first_name}\n📞 {phone}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")]
            ]))
        await auto_setup_profile(session_name)
    except Exception as e:
        await message.answer(f"❌ خطا: {e}")
        await state.clear()
