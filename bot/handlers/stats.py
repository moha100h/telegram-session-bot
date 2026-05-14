from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware
from services.session_manager import get_all_sessions
from services.task_manager import get_all_tasks

router = Router()
router.callback_query.middleware(AdminMiddleware())


@router.callback_query(F.data == "menu_stats")
async def stats_menu(cb: CallbackQuery):
    sessions = await get_all_sessions()
    active   = sum(1 for s in sessions if s.get("active"))
    tasks    = await get_all_tasks()

    by_type = {}
    total_done = total_failed = 0
    for t in tasks:
        tp = t.get("type", "unknown")
        by_type[tp] = by_type.get(tp, 0) + 1
        total_done   += t.get("done", 0)
        total_failed += t.get("failed", 0)

    tnames = {
        "join": "عضویت",
        "group2group": "گروه→گروه",
        "view": "ویو",
        "reaction": "ریاکشن"
    }
    type_lines = "".join(
        f"• {tnames.get(k, k)}: <b>{v}</b> تسک\n"
        for k, v in by_type.items()
    ) or "• هیچ تسکی ثبت نشده\n"

    text = (
        f"📊 <b>آمار کلی</b>\n\n"
        f"📱 سشن فعال: <b>{active}</b> / {len(sessions)}\n"
        f"📋 کل تسک: <b>{len(tasks)}</b>\n"
        f"✅ کل موفق: <b>{total_done}</b>\n"
        f"❌ کل ناموفق: <b>{total_failed}</b>\n\n"
        f"📁 بر اساس نوع:\n{type_lines}"
    )
    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="menu_stats")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )
