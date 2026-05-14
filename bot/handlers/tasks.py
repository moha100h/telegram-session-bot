from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from middlewares.admin import AdminMiddleware
from services.task_manager import get_all_tasks, get_task, cancel_task
from services.session_manager import get_all_sessions, get_session_names
from redis.asyncio import Redis
import json
import uuid
import os

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

TASK_QUEUE = "tsb:task_queue"
DATA_DIR   = os.getenv("DATA_DIR", "/app/data")
TASK_FILE  = os.path.join(DATA_DIR, "tasks.json")


class NewTaskStates(StatesGroup):
    type_sel   = State()
    target     = State()
    source     = State()
    count      = State()
    per_session = State()
    sessions   = State()
    emoji      = State()


def tasks_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ تسک جدید", callback_data="task_new")],
        [InlineKeyboardButton(text="📋 لیست تسک‌ها", callback_data="task_list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_tasks")
async def tasks_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    tasks = await get_all_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    pending = sum(1 for t in tasks if t["status"] == "pending")
    await cb.message.edit_text(
        f"⚙️ <b>مدیریت تسک‌ها</b>\n\n"
        f"▶️ در حال: <b>{running}</b>\n"
        f"⏳ در صف: <b>{pending}</b>\n"
        f"📋 کل: <b>{len(tasks)}</b>",
        parse_mode="HTML",
        reply_markup=tasks_menu_kb()
    )


@router.callback_query(F.data == "task_list")
async def task_list(cb: CallbackQuery):
    tasks = await get_all_tasks()
    if not tasks:
        await cb.message.edit_text(
            "📭 هیچ تسکی وجود ندارد",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")]
            ])
        )
        return
    status_icon = {"running": "▶️", "pending": "⏳", "completed": "✅", "failed": "❌", "cancelled": "⛔"}
    type_name   = {"join": "عضویت", "group2group": "گروه→گروه", "view": "ویو", "reaction": "ریاکشن"}
    buttons = []
    for t in tasks[-20:]:
        icon = status_icon.get(t["status"], "")
        tp   = type_name.get(t["type"], t["type"])
        done = t.get("done", 0)
        total = t.get("count", t.get("total", "?"))
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {tp} | {done}/{total}",
            callback_data=f"task_info_{t['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")])
    await cb.message.edit_text(
        f"📋 <b>لیست تسک‌ها ({len(tasks)} عدد)</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("task_info_"))
async def task_info(cb: CallbackQuery):
    tid  = cb.data.replace("task_info_", "")
    task = await get_task(tid)
    if not task:
        await cb.answer("تسک یافت نشد", show_alert=True)
        return
    type_name = {"join": "عضویت", "group2group": "گروه→گروه", "view": "ویو", "reaction": "ریاکشن"}
    tp    = type_name.get(task["type"], task["type"])
    done  = task.get("done", 0)
    fail  = task.get("failed", 0)
    total = task.get("count", "?")
    status = task.get("status", "?")
    kb = []
    if status in ("running", "pending"):
        kb.append([InlineKeyboardButton(text="⏹ لغو تسک", callback_data=f"task_cancel_{tid}")])
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_list")])
    await cb.message.edit_text(
        f"ℹ️ <b>جزئیات تسک</b>\n\n"
        f"• نوع: {tp}\n"
        f"• وضعیت: {status}\n"
        f"• موفق: <b>{done}</b> | ناموفق: <b>{fail}</b> | کل: <b>{total}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("task_cancel_"))
async def task_cancel(cb: CallbackQuery):
    tid = cb.data.replace("task_cancel_", "")
    await cancel_task(tid)
    await cb.answer("✅ تسک لغو شد")
    await task_list(cb)


# ── New task flow ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "task_new")
async def task_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(NewTaskStates.type_sel)
    await cb.message.edit_text(
        "➕ <b>نوع تسک را انتخاب کنید:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 عضویت گروه/کانال",  callback_data="ttype_join")],
            [InlineKeyboardButton(text="🔄 گروه به گروه",         callback_data="ttype_g2g")],
            [InlineKeyboardButton(text="👁 ویو پست",               callback_data="ttype_view")],
            [InlineKeyboardButton(text="👍 ریاکشن",                  callback_data="ttype_reaction")],
            [InlineKeyboardButton(text="🔙 بازگشت",                  callback_data="menu_tasks")],
        ])
    )


async def _ask_sessions(cb_or_msg, state: FSMContext, redis: Redis):
    names = await get_session_names()
    if not names:
        text = "❌ هیچ سشنی وجود ندارد. ابتدا سشن اضافه کنید."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 افزودن سشن", callback_data="session_add")]
        ])
    else:
        text = (
            f"📱 <b>سشن‌های موجود ({len(names)} عدد)</b>\n\n"
            "عدد سشن مورد نیاز را بفرستید:\n"
            "(0 = همه سشن‌ها)"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="همه سشن‌ها", callback_data="sess_all")]
        ])
    await state.set_state(NewTaskStates.sessions)
    if isinstance(cb_or_msg, CallbackQuery):
        await cb_or_msg.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb_or_msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "ttype_join")
async def ttype_join(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="join")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "📱 <b>عضویت</b>\n\nلینک گروه/کانال را بفرستید:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_g2g")
async def ttype_g2g(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="group2group")
    await state.set_state(NewTaskStates.source)
    await cb.message.edit_text(
        "🔄 <b>گروه به گروه</b>\n\nلینک گروه <b>مبدا</b> را بفرستید:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_view")
async def ttype_view(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="view")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "👁 <b>ویو پست</b>\n\nلینک پست را بفرستید:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_reaction")
async def ttype_reaction(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="reaction")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "👍 <b>ریاکشن</b>\n\nلینک پست را بفرستید:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.message(NewTaskStates.source)
async def task_source(message: Message, state: FSMContext):
    await state.update_data(source=message.text.strip())
    await state.set_state(NewTaskStates.target)
    await message.answer(
        "لینک گروه <b>مقصد</b> را بفرستید:",
        parse_mode="HTML"
    )


@router.message(NewTaskStates.target)
async def task_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    data = await state.get_data()
    if data["type"] in ("join", "group2group"):
        await state.set_state(NewTaskStates.count)
        await message.answer("🔢 تعداد کاربر را وارد کنید:")
    else:
        await state.set_state(NewTaskStates.count)
        await message.answer("🔢 تعداد سشن را وارد کنید (0=همه):")


@router.message(NewTaskStates.count)
async def task_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    await state.update_data(count=count)
    data = await state.get_data()
    if data["type"] == "group2group":
        await state.set_state(NewTaskStates.per_session)
        await message.answer("📱 هر سشن چند نفر اد کند? (5-20 پیشنهاد):")
    elif data["type"] == "reaction":
        await state.set_state(NewTaskStates.emoji)
        await message.answer("👍 ایموجی ریاکشن را بفرستید (\u0645ثال: 👍 🔥 ❤️):")
    else:
        await _ask_sessions(message, state, redis)


@router.message(NewTaskStates.per_session)
async def task_per_session(message: Message, state: FSMContext, redis: Redis):
    try:
        per = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    await state.update_data(per_session=per)
    await _ask_sessions(message, state, redis)


@router.message(NewTaskStates.emoji)
async def task_emoji(message: Message, state: FSMContext, redis: Redis):
    await state.update_data(emoji=message.text.strip())
    await _ask_sessions(message, state, redis)


@router.callback_query(F.data == "sess_all", NewTaskStates.sessions)
async def task_sess_all(cb: CallbackQuery, state: FSMContext, redis: Redis):
    names = await get_session_names()
    await state.update_data(sessions=names)
    await _submit_task(cb, state, redis)


@router.message(NewTaskStates.sessions)
async def task_sessions_count(message: Message, state: FSMContext, redis: Redis):
    try:
        n = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    names = await get_session_names()
    selected = names if n == 0 else names[:n]
    await state.update_data(sessions=selected)
    await _submit_task(message, state, redis)


async def _submit_task(cb_or_msg, state: FSMContext, redis: Redis):
    import aiofiles
    data = await state.get_data()
    await state.clear()
    tid  = uuid.uuid4().hex[:8]
    task = {
        "id":      tid,
        "type":    data["type"],
        "status":  "pending",
        "done":    0,
        "failed":  0,
        "count":   data.get("count", 0),
        "target":  data.get("target", ""),
        "source":  data.get("source", ""),
        "dest":    data.get("target", ""),
        "sessions": data.get("sessions", []),
        "per_session": data.get("per_session", 10),
        "emoji":   data.get("emoji", "👍"),
    }
    # Save to tasks.json
    os.makedirs(DATA_DIR, exist_ok=True)
    tasks = {}
    if os.path.exists(TASK_FILE):
        try:
            async with aiofiles.open(TASK_FILE, "r") as f:
                tasks = json.loads(await f.read())
        except Exception:
            pass
    tasks[tid] = task
    async with aiofiles.open(TASK_FILE, "w") as f:
        await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))
    # Push to worker queue
    await redis.rpush(TASK_QUEUE, json.dumps(task))
    type_name = {"join": "عضویت", "group2group": "گروه→گروه", "view": "ویو", "reaction": "ریاکشن"}
    tp = type_name.get(task["type"], task["type"])
    text = (
        f"✅ <b>تسک ایجاد شد</b>\n\n"
        f"• نوع: {tp}\n"
        f"• تعداد: {task['count']}\n"
        f"• سشن: {len(task['sessions'])} عدد\n"
        f"• شناسه: <code>{tid}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 لیست تسک‌ها", callback_data="task_list")],
        [InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="menu_main")],
    ])
    if isinstance(cb_or_msg, CallbackQuery):
        await cb_or_msg.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb_or_msg.answer(text, parse_mode="HTML", reply_markup=kb)
