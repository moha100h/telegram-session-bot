from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MenuButtonWebApp, MenuButtonCommands, BotCommand
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from middlewares.admin import AdminMiddleware
from services.session_manager import get_active_sessions, get_all_sessions
from services.task_manager import get_all_tasks
import os

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 سشن‌ها", callback_data="menu_sessions"),
            InlineKeyboardButton(text="⚙️ تسک‌ها", callback_data="menu_tasks"),
        ],
        [
            InlineKeyboardButton(text="🌐 پروکسی", callback_data="menu_proxy"),
            InlineKeyboardButton(text="📊 آمار", callback_data="menu_stats"),
        ],
        [
            InlineKeyboardButton(text="💾 بکاپ", callback_data="menu_backup"),
            InlineKeyboardButton(text="📞 شماره مجازی", callback_data="menu_virtual"),
        ],
        [
            InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="menu_refresh"),
        ],
    ])


async def build_status_text(bot) -> str:
    sessions = await get_all_sessions()
    active   = [s for s in sessions if s.get("active")]
    tasks    = await get_all_tasks()
    running  = [t for t in tasks if t["status"] == "running"]
    pending  = [t for t in tasks if t["status"] == "pending"]
    done     = [t for t in tasks if t["status"] == "completed"]

    me = await bot.get_me()
    return (
        f"🤖 <b>{me.first_name}</b> | @{me.username}\n"
        f"────────────────────\n"
        f"📱 سشن‌ها: <b>{len(active)}</b> فعال / {len(sessions)} کل\n"
        f"▶️ تسک در حال: <b>{len(running)}</b>\n"
        f"⏳ در صف: <b>{len(pending)}</b>\n"
        f"✅ تمام شده: <b>{len(done)}</b>\n"
        f"────────────────────\n"
        f"📦 یک بخش را انتخاب کنید:"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot):
    await state.clear()
    text = await build_status_text(bot)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, bot):
    await state.clear()
    text = await build_status_text(bot)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu_main")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext, bot):
    await state.clear()
    text = await build_status_text(bot)
    await cb.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "menu_refresh")
async def cb_refresh(cb: CallbackQuery, state: FSMContext, bot):
    await state.clear()
    text = await build_status_text(bot)
    await cb.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await cb.answer("✅ به‌روز شد")
