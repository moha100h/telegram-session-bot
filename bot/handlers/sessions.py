from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from middlewares.admin import AdminMiddleware
from services.session_manager import (
    get_all_sessions, check_session, delete_session,
    update_session_meta, auto_setup_profile, get_active_sessions)
import os
from config import SESSIONS_DIR

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

class SessionStates(StatesGroup):
    waiting_file = State()
    waiting_delete = State()

def sessions_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 آپلود سشن", callback_data="sess_upload")],
        [InlineKeyboardButton(text="📋 لیست سشن‌ها", callback_data="sess_list")],
        [InlineKeyboardButton(text="🔍 بررسی همه", callback_data="sess_check_all")],
        [InlineKeyboardButton(text="🤖 پروفایل خودکار همه", callback_data="sess_auto_all")],
        [InlineKeyboardButton(text="🗑 حذف سشن", callback_data="sess_delete_menu")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_sessions")
async def sessions_menu_cb(cb: CallbackQuery):
    sessions = await get_all_sessions()
    active = sum(1 for s in sessions if s.get("status") == "active")
    banned = sum(1 for s in sessions if s.get("status") == "banned")
    await cb.message.edit_text(
        f"📱 <b>مدیریت سشن‌ها</b>\n\n✅ فعال: <b>{active}</b>\n🚫 بن: <b>{banned}</b>\n📦 کل: <b>{len(sessions)}</b>",
        reply_markup=sessions_menu(), parse_mode="HTML")

@router.callback_query(F.data == "sess_upload")
async def sess_upload(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📤 فایل <code>.session</code> را ارسال کنید\n(می‌توانید چند فایل پشت سر هم بفرستید)", parse_mode="HTML")
    await state.set_state(SessionStates.waiting_file)

@router.message(SessionStates.waiting_file, F.document)
async def sess_receive_file(message: Message, state: FSMContext):
    doc = message.document
    if not doc.file_name.endswith(".session"):
        await message.answer("❌ فقط فایل .session قبول می‌شود")
        return
    session_name = doc.file_name[:-8]
    dest = os.path.join(SESSIONS_DIR, doc.file_name)
    await message.bot.download(doc, destination=dest)
    msg = await message.answer(f"🔍 بررسی سشن <code>{session_name}</code>...", parse_mode="HTML")
    result = await check_session(session_name)
    if result["status"] == "active":
        await update_session_meta(session_name, {"status": "active", "phone": result.get("phone"),
            "username": result.get("username"), "first_name": result.get("first_name"), "tg_id": result.get("id")})
        await msg.edit_text(
            f"✅ سشن فعال\n👤 {result.get('first_name','')} | @{result.get('username','ندارد')}\n📞 {result.get('phone','')}",
            parse_mode="HTML")
    else:
        await update_session_meta(session_name, {"status": result["status"]})
        await msg.edit_text(f"⚠️ وضعیت: <code>{result['status']}</code>\n{result.get('error','')}", parse_mode="HTML")

@router.callback_query(F.data == "sess_list")
async def sess_list(cb: CallbackQuery):
    sessions = await get_all_sessions()
    if not sessions:
        await cb.message.edit_text("📭 هیچ سشنی وجود ندارد", reply_markup=sessions_menu())
        return
    text = "📋 <b>لیست سشن‌ها:</b>\n\n"
    for i, s in enumerate(sessions[:30], 1):
        icon = "✅" if s.get("status") == "active" else "🚫" if s.get("status") == "banned" else "⚠️"
        text += f"{i}. {icon} <code>{s['name']}</code> | {s.get('first_name','?')} | {s.get('phone','')}\n"
    if len(sessions) > 30:
        text += f"\n... و {len(sessions)-30} سشن دیگر"
    await cb.message.edit_text(text, reply_markup=sessions_menu(), parse_mode="HTML")

@router.callback_query(F.data == "sess_check_all")
async def sess_check_all(cb: CallbackQuery):
    sessions = await get_all_sessions()
    if not sessions:
        await cb.answer("هیچ سشنی وجود ندارد")
        return
    msg = await cb.message.edit_text(f"🔍 بررسی {len(sessions)} سشن...")
    active = banned = error = 0
    for s in sessions:
        r = await check_session(s["name"])
        if r["status"] == "active":
            active += 1
            await update_session_meta(s["name"], {"status": "active", "phone": r.get("phone"), "username": r.get("username")})
        elif "banned" in str(r.get("error", "")).lower():
            banned += 1
            await update_session_meta(s["name"], {"status": "banned"})
        else:
            error += 1
            await update_session_meta(s["name"], {"status": r["status"]})
    await msg.edit_text(
        f"✅ بررسی کامل\n\n✅ فعال: {active}\n🚫 بن: {banned}\n⚠️ خطا: {error}",
        reply_markup=sessions_menu())

@router.callback_query(F.data == "sess_auto_all")
async def sess_auto_all(cb: CallbackQuery):
    sessions = await get_active_sessions()
    fresh = [s for s in sessions if not s.get("auto_setup")]
    if not fresh:
        await cb.answer("همه سشن‌ها قبلاً پروفایل دارند")
        return
    msg = await cb.message.edit_text(f"🤖 تنظیم پروفایل برای {len(fresh)} سشن...")
    done = 0
    for s in fresh:
        if await auto_setup_profile(s["name"]):
            done += 1
    await msg.edit_text(f"✅ پروفایل {done}/{len(fresh)} سشن تنظیم شد", reply_markup=sessions_menu())

@router.callback_query(F.data == "sess_delete_menu")
async def sess_delete_menu(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🗑 نام سشن را برای حذف بفرستید (بدون .session):")
    await state.set_state(SessionStates.waiting_delete)

@router.message(SessionStates.waiting_delete)
async def sess_delete_confirm(message: Message, state: FSMContext):
    name = message.text.strip()
    await delete_session(name)
    await state.clear()
    await message.answer(f"✅ سشن <code>{name}</code> حذف شد", parse_mode="HTML", reply_markup=sessions_menu())
