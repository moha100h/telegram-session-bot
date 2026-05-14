from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from middlewares.admin import AdminMiddleware
from services.task_manager import create_task, get_all_tasks, cancel_task, get_task
from services.session_manager import get_active_sessions
from redis.asyncio import Redis

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

class TaskStates(StatesGroup):
    join_target = State()
    join_count = State()
    g2g_source = State()
    g2g_dest = State()
    g2g_count = State()
    g2g_per_session = State()
    view_target = State()
    view_count = State()
    reaction_target = State()
    reaction_emoji = State()
    reaction_count = State()

def tasks_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 عضویت در کانال/گروه", callback_data="task_join")],
        [InlineKeyboardButton(text="🔄 گروه به گروه", callback_data="task_g2g")],
        [InlineKeyboardButton(text="👁 ویو پست", callback_data="task_view")],
        [InlineKeyboardButton(text="👍 ریاکشن", callback_data="task_reaction")],
        [InlineKeyboardButton(text="📋 لیست تسک‌ها", callback_data="task_list")],
        [InlineKeyboardButton(text="❌ لغو تسک", callback_data="task_cancel_menu")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])

@router.callback_query(F.data == "menu_tasks")
async def tasks_menu_cb(cb: CallbackQuery):
    tasks = await get_all_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    pending = sum(1 for t in tasks if t["status"] == "pending")
    done = sum(1 for t in tasks if t["status"] == "completed")
    await cb.message.edit_text(
        f"⚙️ <b>مدیریت تسک‌ها</b>\n\n▶️ در حال اجرا: <b>{running}</b>\n⏳ در صف: <b>{pending}</b>\n✅ تمام شده: <b>{done}</b>",
        reply_markup=tasks_menu(), parse_mode="HTML")

# ── JOIN TASK ────────────────────────────────────────────────────
@router.callback_query(F.data == "task_join")
async def task_join_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📥 لینک کانال/گروه مقصد را بفرستید:\nمثال: @channel یا https://t.me/channel")
    await state.set_state(TaskStates.join_target)

@router.message(TaskStates.join_target)
async def task_join_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    sessions = await get_active_sessions()
    await message.answer(f"📊 تعداد سشن فعال: {len(sessions)}\nچند سشن عضو شوند? (0 = همه)")
    await state.set_state(TaskStates.join_count)

@router.message(TaskStates.join_count)
async def task_join_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    data = await state.get_data()
    await state.clear()
    sessions = await get_active_sessions()
    use_sessions = sessions[:count] if count > 0 else sessions
    tid = await create_task(redis, {
        "type": "join",
        "target": data["target"],
        "sessions": [s["name"] for s in use_sessions],
        "total": len(use_sessions),
    })
    await message.answer(
        f"✅ تسک عضویت ساخته شد\n🆔 ID: <code>{tid}</code>\n📱 سشن: {len(use_sessions)}\n🎯 مقصد: {data['target']}",
        parse_mode="HTML", reply_markup=tasks_menu())

# ── GROUP TO GROUP ───────────────────────────────────────────────
@router.callback_query(F.data == "task_g2g")
async def task_g2g_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔄 آیدی گروه مبدا را بفرستید:\n(آیدی عددی گروه یا لینک)")
    await state.set_state(TaskStates.g2g_source)

@router.message(TaskStates.g2g_source)
async def task_g2g_source(message: Message, state: FSMContext):
    await state.update_data(source=message.text.strip())
    await message.answer("🎯 آیدی گروه مقصد را بفرستید:")
    await state.set_state(TaskStates.g2g_dest)

@router.message(TaskStates.g2g_dest)
async def task_g2g_dest(message: Message, state: FSMContext):
    await state.update_data(dest=message.text.strip())
    await message.answer("📊 تعداد کل کاربر برای انتقال:")
    await state.set_state(TaskStates.g2g_count)

@router.message(TaskStates.g2g_count)
async def task_g2g_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    await state.update_data(count=count)
    await message.answer("📱 هر سشن چند نفر اد کند? (10-50 پیشنهاد)")
    await state.set_state(TaskStates.g2g_per_session)

@router.message(TaskStates.g2g_per_session)
async def task_g2g_per_session(message: Message, state: FSMContext, redis: Redis):
    try:
        per = int(message.text.strip())
        per = max(1, min(50, per))
    except ValueError:
        per = 20
    data = await state.get_data()
    await state.clear()
    sessions = await get_active_sessions()
    tid = await create_task(redis, {
        "type": "group2group",
        "source": data["source"],
        "dest": data["dest"],
        "count": data["count"],
        "per_session": per,
        "sessions": [s["name"] for s in sessions],
        "total": data["count"],
    })
    await message.answer(
        f"✅ تسک گروه به گروه ساخته شد\n🆔 ID: <code>{tid}</code>\n📊 تعداد: {data['count']}\n📱 هر سشن: {per} نفر",
        parse_mode="HTML", reply_markup=tasks_menu())

# ── VIEW POST ────────────────────────────────────────────────────
@router.callback_query(F.data == "task_view")
async def task_view_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("👁 لینک پست را بفرستید:\nمثال: https://t.me/channel/123")
    await state.set_state(TaskStates.view_target)

@router.message(TaskStates.view_target)
async def task_view_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await message.answer("📊 تعداد ویو:")
    await state.set_state(TaskStates.view_count)

@router.message(TaskStates.view_count)
async def task_view_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    data = await state.get_data()
    await state.clear()
    sessions = await get_active_sessions()
    tid = await create_task(redis, {
        "type": "view",
        "target": data["target"],
        "count": count,
        "sessions": [s["name"] for s in sessions[:count]],
        "total": count,
    })
    await message.answer(
        f"✅ تسک ویو ساخته شد\n🆔 ID: <code>{tid}</code>\n👁 تعداد: {count}",
        parse_mode="HTML", reply_markup=tasks_menu())

# ── REACTION ─────────────────────────────────────────────────────
@router.callback_query(F.data == "task_reaction")
async def task_reaction_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("👍 لینک پست را بفرستید:")
    await state.set_state(TaskStates.reaction_target)

@router.message(TaskStates.reaction_target)
async def task_reaction_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await message.answer("😊 ایموجی ریاکشن را بفرستید:\nمثال: 👍 یا ❤️ یا 🔥")
    await state.set_state(TaskStates.reaction_emoji)

@router.message(TaskStates.reaction_emoji)
async def task_reaction_emoji(message: Message, state: FSMContext):
    await state.update_data(emoji=message.text.strip())
    await message.answer("📊 تعداد ریاکشن:")
    await state.set_state(TaskStates.reaction_count)

@router.message(TaskStates.reaction_count)
async def task_reaction_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    data = await state.get_data()
    await state.clear()
    sessions = await get_active_sessions()
    tid = await create_task(redis, {
        "type": "reaction",
        "target": data["target"],
        "emoji": data["emoji"],
        "count": count,
        "sessions": [s["name"] for s in sessions[:count]],
        "total": count,
    })
    await message.answer(
        f"✅ تسک ریاکشن ساخته شد\n🆔 ID: <code>{tid}</code>\n{data['emoji']} تعداد: {count}",
        parse_mode="HTML", reply_markup=tasks_menu())

# ── LIST & CANCEL ────────────────────────────────────────────────
@router.callback_query(F.data == "task_list")
async def task_list(cb: CallbackQuery):
    tasks = await get_all_tasks()
    if not tasks:
        await cb.message.edit_text("📭 هیچ تسکی وجود ندارد", reply_markup=tasks_menu())
        return
    text = "📋 <b>لیست تسک‌ها:</b>\n\n"
    icons = {"pending": "⏳", "running": "▶️", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
    type_names = {"join": "عضویت", "group2group": "گروه→گروه", "view": "ویو", "reaction": "ریاکشن"}
    for t in tasks[-20:]:
        icon = icons.get(t["status"], "?‏")
        tname = type_names.get(t["type"], t["type"])
        text += f"{icon} <code>{t['id']}</code> | {tname} | انجام: {t.get('done',0)}/{t.get('total',0)}\n"
    await cb.message.edit_text(text, reply_markup=tasks_menu(), parse_mode="HTML")

@router.callback_query(F.data == "task_cancel_menu")
async def task_cancel_menu(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("❌ ID تسک را بفرستید:")
    await state.set_state(TaskStates.join_target)

@router.message(TaskStates.join_target)
async def task_cancel_do(message: Message, state: FSMContext, redis: Redis):
    tid = message.text.strip()
    task = await get_task(tid)
    if not task:
        await message.answer("❌ تسک یافت نشد")
        await state.clear()
        return
    await cancel_task(redis, tid)
    await state.clear()
    await message.answer(f"✅ تسک <code>{tid}</code> لغو شد", parse_mode="HTML", reply_markup=tasks_menu())
