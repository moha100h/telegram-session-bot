from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 سشن‌ها", callback_data="menu_sessions"),
         InlineKeyboardButton(text="⚙️ تسک‌ها", callback_data="menu_tasks")],
        [InlineKeyboardButton(text="📊 آمار", callback_data="menu_stats"),
         InlineKeyboardButton(text="🌐 پروکسی", callback_data="menu_proxy")],
        [InlineKeyboardButton(text="📲 شماره مجازی", callback_data="menu_vnumber"),
         InlineKeyboardButton(text="🗄 بکاپ", callback_data="menu_backup")],
    ])

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🤖 <b>Session Manager Bot</b>\n\nسیستم مدیریت سشن تلگرام\nاز منوی زیر انتخاب کنید:",
        reply_markup=main_menu(), parse_mode="HTML")

@router.callback_query(F.data == "menu_main")
async def menu_main(cb: CallbackQuery):
    await cb.message.edit_text(
        "🤖 <b>Session Manager Bot</b>\n\nاز منوی زیر انتخاب کنید:",
        reply_markup=main_menu(), parse_mode="HTML")
