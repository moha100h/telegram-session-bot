import os
from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 سشن‌ها",    callback_data="menu_sessions"),
            InlineKeyboardButton(text="⚙️ تسک‌ها",    callback_data="menu_tasks"),
        ],
        [
            InlineKeyboardButton(text="📊 آمار",       callback_data="menu_stats"),
            InlineKeyboardButton(text="💾 بکاپ",       callback_data="menu_backup"),
        ],
        [
            InlineKeyboardButton(text="🌐 پروکسی",     callback_data="menu_proxy"),
            InlineKeyboardButton(text="📞 شماره مجازی", callback_data="menu_virtual"),
        ],
        [
            InlineKeyboardButton(text="🔥 Warmer",      callback_data="menu_warmer"),
            InlineKeyboardButton(text="🤖 خرید سشن",   callback_data="menu_autosession"),
        ],
        [
            InlineKeyboardButton(text="📸 اینستاگرام و یوتیوب", callback_data="menu_social"),
        ],
        [
            InlineKeyboardButton(text="🛠 FJPanel — پنل SMM", callback_data="menu_fjpanel"),
        ],
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"⛔️ دسترسی ندارید\nID شما: <code>{message.from_user.id}</code>", parse_mode="HTML")
        return
    await message.answer(
        "🤖 <b>Telegram Session Bot</b>\n\n"
        "خوش آمدید! از منوی زیر استفاده کنید:",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"⛔️ دسترسی ندارید\nID شما: <code>{message.from_user.id}</code>", parse_mode="HTML")
        return
    await message.answer(
        "🤖 <b>منوی اصلی</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


@router.callback_query(lambda c: c.data == "menu_main")
async def menu_main(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    await cb.message.edit_text(
        "🤖 <b>منوی اصلی</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )
