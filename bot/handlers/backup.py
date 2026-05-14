from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from middlewares.admin import AdminMiddleware
from services.backup import BackupService
from redis.asyncio import Redis
import os, zipfile
from config import SESSIONS_DIR, DATA_DIR

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

class BackupStates(StatesGroup):
    waiting_restore = State()

def backup_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 بکاپ الان", callback_data="backup_now")],
        [InlineKeyboardButton(text="📥 بازگردانی بکاپ", callback_data="backup_restore")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_backup")
async def backup_menu_cb(cb: CallbackQuery):
    await cb.message.edit_text("🗄 <b>مدیریت بکاپ</b>\n\nبکاپ خودکار هر ۱ ساعت ارسال می‌شود",
        reply_markup=backup_menu(), parse_mode="HTML")

@router.callback_query(F.data == "backup_now")
async def backup_now(cb: CallbackQuery, redis: Redis):
    msg = await cb.message.edit_text("📦 در حال ساخت بکاپ...")
    svc = BackupService(cb.bot, redis)
    await svc.send_backup()
    await msg.edit_text("✅ بکاپ ارسال شد", reply_markup=backup_menu())

@router.callback_query(F.data == "backup_restore")
async def backup_restore_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📥 فایل بکاپ (.zip) را ارسال کنید:")
    await state.set_state(BackupStates.waiting_restore)

@router.message(BackupStates.waiting_restore, F.document)
async def backup_restore_do(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.endswith(".zip"):
        await message.answer("❌ فقط فایل .zip قبول می‌شود")
        return
    msg = await message.answer("📥 در حال بازگردانی...")
    import io
    buf = io.BytesIO()
    await message.bot.download(doc, destination=buf)
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        for name in zf.namelist():
            if name.startswith("sessions/"):
                zf.extract(name, "/app")
            elif name.startswith("data/"):
                zf.extract(name, "/app")
    await state.clear()
    await msg.edit_text("✅ بکاپ با موفقیت بازگردانی شد", reply_markup=backup_menu())
