from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware
from services.backup import BackupService
from redis.asyncio import Redis

router = Router()
router.callback_query.middleware(AdminMiddleware())


@router.callback_query(F.data == "menu_backup")
async def backup_menu(cb: CallbackQuery, redis: Redis):
    await cb.message.edit_text(
        "💾 <b>مدیریت بکاپ</b>\n\n"
        "• بکاپ خودکار هر ۱ ساعت\n"
        "• شامل: سشن‌ها + دیتابیس",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💾 بکاپ الان", callback_data="backup_now")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )


@router.callback_query(F.data == "backup_now")
async def backup_now(cb: CallbackQuery, redis: Redis, bot):
    await cb.message.edit_text("⏳ در حال تهیه بکاپ...")
    svc = BackupService(bot, redis)
    await svc.do_backup()
    await cb.message.edit_text(
        "✅ بکاپ انجام شد",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )
