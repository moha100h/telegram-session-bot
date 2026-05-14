from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware
from services.proxy_fetcher import ProxyFetcher
from redis.asyncio import Redis

router = Router()
router.callback_query.middleware(AdminMiddleware())

@router.callback_query(F.data == "menu_proxy")
async def proxy_menu(cb: CallbackQuery, redis: Redis):
    pf = ProxyFetcher(redis)
    count = await pf.count()
    sample = await pf.get_random()
    sample_text = f"🔹 نمونه: <code>{sample['host']}:{sample['port']}</code>" if sample else "⚠️ هیچ پروکسی موجود نیست"
    await cb.message.edit_text(
        f"🌐 <b>مدیریت پروکسی</b>\n\n📊 تعداد: <b>{count}</b>\n{sample_text}\n\nبه‌روزرسانی خودکار هر ۱ ساعت",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 به‌روزرسانی الان", callback_data="proxy_refresh")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ]))

@router.callback_query(F.data == "proxy_refresh")
async def proxy_refresh(cb: CallbackQuery, redis: Redis):
    msg = await cb.message.edit_text("🔄 در حال دریافت پروکسی...")
    pf = ProxyFetcher(redis)
    await pf.refresh()
    count = await pf.count()
    await msg.edit_text(f"✅ لیست پروکسی به‌روز شد\n📊 تعداد: {count}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_proxy")],
        ]))
