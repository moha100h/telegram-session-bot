from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware
from services.session_manager import get_all_sessions
from services.task_manager import get_all_tasks
from services.proxy_fetcher import ProxyFetcher
from redis.asyncio import Redis

router = Router()
router.callback_query.middleware(AdminMiddleware())

@router.callback_query(F.data == "menu_stats")
async def stats_menu(cb: CallbackQuery, redis: Redis):
    sessions = await get_all_sessions()
    tasks = await get_all_tasks()
    pf = ProxyFetcher(redis)
    proxy_count = await pf.count()

    active_s = sum(1 for s in sessions if s.get("status") == "active")
    banned_s = sum(1 for s in sessions if s.get("status") == "banned")
    error_s = len(sessions) - active_s - banned_s

    running_t = sum(1 for t in tasks if t["status"] == "running")
    pending_t = sum(1 for t in tasks if t["status"] == "pending")
    done_t = sum(1 for t in tasks if t["status"] == "completed")
    failed_t = sum(1 for t in tasks if t["status"] == "failed")
    total_done = sum(t.get("done", 0) for t in tasks)
    total_failed = sum(t.get("failed", 0) for t in tasks)

    text = (
        f"📊 <b>آمار کلی</b>\n\n"
        f"📱 <b>سشن‌ها:</b>\n"
        f"  ✅ فعال: {active_s}\n"
        f"  🚫 بن: {banned_s}\n"
        f"  ⚠️ خطا: {error_s}\n"
        f"  📦 کل: {len(sessions)}\n\n"
        f"⚙️ <b>تسک‌ها:</b>\n"
        f"  ▶️ در حال: {running_t}\n"
        f"  ⏳ در صف: {pending_t}\n"
        f"  ✅ تمام: {done_t}\n"
        f"  ❌ شکست: {failed_t}\n"
        f"  📊 کل انجام: {total_done} | شکست: {total_failed}\n\n"
        f"🌐 <b>پروکسی:</b> {proxy_count} عدد"
    )
    await cb.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="menu_stats")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ]))
