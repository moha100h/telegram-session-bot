import os
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot
from redis.asyncio import Redis
from services.backup import BackupService

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


@router.callback_query(F.data == "menu_backup")
async def backup_menu(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    await cb.message.edit_text(
        "💾 <b>بکاپ</b>\n\n"
        "• بکاپ خودکار هر ۱ ساعت\n"
        "• شامل: سشن‌ها + دیتابیس",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💾 بکاپ الان", callback_data="backup_now")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )


@router.callback_query(F.data == "backup_now")
async def backup_now(cb: CallbackQuery, bot: Bot, redis: Redis):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️ دسترسی ندارید", show_alert=True)
        return
    await cb.message.edit_text("⏳ در حال تهیه بکاپ...")
    svc = BackupService(bot, redis)
    await svc.do_backup()
    await cb.message.edit_text(
        "✅ بکاپ ارسال شد",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_backup")]
        ])
    )
