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
            InlineKeyboardButton(text="\U0001f4f1 \u0633\u0634\u0646\u200c\u0647\u0627",    callback_data="menu_sessions"),
            InlineKeyboardButton(text="\u2699\ufe0f \u062a\u0633\u06a9\u200c\u0647\u0627",    callback_data="menu_tasks"),
        ],
        [
            InlineKeyboardButton(text="\U0001f4ca \u0622\u0645\u0627\u0631",       callback_data="menu_stats"),
            InlineKeyboardButton(text="\U0001f4be \u0628\u06a9\u0627\u067e",       callback_data="menu_backup"),
        ],
        [
            InlineKeyboardButton(text="\U0001f310 \u067e\u0631\u0648\u06a9\u0633\u06cc",     callback_data="menu_proxy"),
            InlineKeyboardButton(text="\U0001f4de \u0634\u0645\u0627\u0631\u0647 \u0645\u062c\u0627\u0632\u06cc", callback_data="menu_virtual"),
        ],
        [
            InlineKeyboardButton(text="\U0001f525 Warmer",      callback_data="menu_warmer"),
            InlineKeyboardButton(text="\U0001f916 \u062e\u0631\u06cc\u062f \u0633\u0634\u0646",   callback_data="menu_autosession"),
        ],
        [
            InlineKeyboardButton(text="\U0001f4f8 \u0627\u06cc\u0646\u0633\u062a\u0627\u06af\u0631\u0627\u0645 \u0648 \u06cc\u0648\u062a\u06cc\u0648\u0628", callback_data="menu_social"),
        ],
        [
            InlineKeyboardButton(text="\U0001f6e0 FJPanel \u2014 \u067e\u0646\u0644 SMM",  callback_data="menu_fjpanel"),
            InlineKeyboardButton(text="\U0001f680 SMMPass",                callback_data="menu_smmpass"),
        ],
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f\nID \u0634\u0645\u0627: <code>{message.from_user.id}</code>", parse_mode="HTML")
        return
    await message.answer(
        "\U0001f916 <b>Telegram Session Bot</b>\n\n"
        "\u062e\u0648\u0634 \u0622\u0645\u062f\u06cc\u062f! \u0627\u0632 \u0645\u0646\u0648\u06cc \u0632\u06cc\u0631 \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f:",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f\nID \u0634\u0645\u0627: <code>{message.from_user.id}</code>", parse_mode="HTML")
        return
    await message.answer(
        "\U0001f916 <b>\u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


@router.callback_query(lambda c: c.data == "menu_main")
async def menu_main(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f", show_alert=True)
        return
    await cb.message.edit_text(
        "\U0001f916 <b>\u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc</b>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )
