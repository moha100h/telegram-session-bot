import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from services.session_manager import get_all_sessions, get_active_sessions
from services.task_manager import get_all_tasks

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


@router.callback_query(F.data == "menu_stats")
async def stats_menu(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    sessions = await get_all_sessions()
    active   = await get_active_sessions()
    tasks    = await get_all_tasks()
    running  = sum(1 for t in tasks if t["status"] == "running")
    done     = sum(1 for t in tasks if t["status"] == "completed")
    await cb.message.edit_text(
        "📊 <b>آمار کلی</b>\n\n"
        f"📱 سشن کل: <b>{len(sessions)}</b>\n"
        f"✅ سشن فعال: <b>{len(active)}</b>\n"
        f"⚙️ تسک در حال: <b>{running}</b>\n"
        f"✅ تسک انجام شده: <b>{done}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")]
        ])
    )
