import os
import json
import uuid
import time
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from middlewares.admin import AdminMiddleware
from services.task_manager import get_all_tasks, get_task, cancel_task
from services.session_manager import get_session_names
from redis.asyncio import Redis

router = Router()
router.message.middleware(AdminMiddleware())
router.callback_query.middleware(AdminMiddleware())

TASK_QUEUE = "tsb:task_queue"
DATA_DIR   = os.getenv("DATA_DIR", "/app/data")
TASK_FILE  = os.path.join(DATA_DIR, "tasks.json")
STATS_FILE = os.path.join(DATA_DIR, "daily_stats.json")


class NewTaskStates(StatesGroup):
    type_sel      = State()
    target        = State()
    source        = State()
    count         = State()
    per_session   = State()
    sessions      = State()
    emoji         = State()
    bot_target    = State()
    report_target = State()
    report_reason = State()


TYPE_FA = {
    "join":        "عضویت",
    "group2group": "گروه→گروه",
    "view":        "ویو",
    "reaction":    "ریاکشن",
    "leave":       "خروج",
    "add_bot":     "اد بات",
    "report":      "ریپورت",
}

STATUS_ICON = {
    "running":   "▶️",
    "pending":   "⏳",
    "completed": "✅",
    "failed":    "❌",
    "cancelled": "⛔",
}


def _load_stats():
    try:
        if os.path.exists(STATS_FILE):
            return json.load(open(STATS_FILE))
    except Exception:
        pass
    return {}


def _save_stats(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _today_key():
    import datetime
    return datetime.date.today().isoformat()


def record_task_done(task_type, done, failed):
    stats = _load_stats()
    key = _today_key()
    if key not in stats:
        stats[key] = {}
    d = stats[key]
    if task_type not in d:
        d[task_type] = {"done": 0, "failed": 0}
    d[task_type]["done"] += done
    d[task_type]["failed"] += failed
    _save_stats(stats)


async def _cleanup_old_tasks():
    if not os.path.exists(TASK_FILE):
        return
    try:
        tasks = json.load(open(TASK_FILE))
        now = time.time()
        kept = []
        for t in tasks:
            status = t.get("status", "")
            finished_at = t.get("finished_at", 0)
            if status in ("completed", "failed", "cancelled"):
                if now - finished_at < 86400:
                    kept.append(t)
            else:
                kept.append(t)
        with open(TASK_FILE, "w") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def tasks_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ تسک جدید",      callback_data="task_new")],
        [InlineKeyboardButton(text="📋 لیست تسک‌ها", callback_data="task_list")],
        [InlineKeyboardButton(text="📊 آمار امروز",  callback_data="task_daily_stats")],
        [InlineKeyboardButton(text="🔙 بازگشت",         callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_tasks")
async def tasks_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _cleanup_old_tasks()
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


@router.callback_query(F.data == "task_daily_stats")
async def task_daily_stats(cb: CallbackQuery):
    stats = _load_stats()
    key = _today_key()
    today = stats.get(key, {})
    if not today:
        text = "📊 <b>آمار امروز</b>\n\nهیچ تسکی امروز انجام نشده"
    else:
        lines = [f"📊 <b>آمار امروز ({key})</b>\n"]
        for tp, vals in today.items():
            name = TYPE_FA.get(tp, tp)
            lines.append(f"• {name}: ✅{vals.get('done', 0)} | ❌{vals.get('failed', 0)}")
        text = "\n".join(lines)
    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")]
        ])
    )


@router.callback_query(F.data == "task_list")
async def task_list(cb: CallbackQuery):
    await _cleanup_old_tasks()
    tasks = await get_all_tasks()
    if not tasks:
        await cb.message.edit_text(
            "📭 هیچ تسکی وجود ندارد",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")]
            ])
        )
        return
    buttons = []
    for t in tasks[-20:]:
        icon  = STATUS_ICON.get(t["status"], "")
        tp    = TYPE_FA.get(t["type"], t["type"])
        done  = t.get("done", 0)
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
    tp     = TYPE_FA.get(task["type"], task["type"])
    done   = task.get("done", 0)
    fail   = task.get("failed", 0)
    total  = task.get("count", "?")
    status = task.get("status", "?")
    target = task.get("target", "-")
    kb = []
    if status in ("running", "pending"):
        kb.append([InlineKeyboardButton(text="⏹ لغو تسک", callback_data=f"task_cancel_{tid}")])
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_list")])
    await cb.message.edit_text(
        f"ℹ️ <b>جزئیات تسک</b>\n\n"
        f"• نوع: {tp}\n"
        f"• هدف: <code>{target}</code>\n"
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


@router.callback_query(F.data == "task_new")
async def task_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(NewTaskStates.type_sel)
    await cb.message.edit_text(
        "➕ <b>نوع تسک را انتخاب کنید:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 عضویت گروه/کانال", callback_data="ttype_join")],
            [InlineKeyboardButton(text="🔄 گروه به گروه",       callback_data="ttype_g2g")],
            [InlineKeyboardButton(text="👁 ویو پست",             callback_data="ttype_view")],
            [InlineKeyboardButton(text="👍 ریاکشن",                callback_data="ttype_reaction")],
            [InlineKeyboardButton(text="🚪 خروج از گروه/کانال", callback_data="ttype_leave")],
            [InlineKeyboardButton(text="🤖 اد به بات",        callback_data="ttype_add_bot")],
            [InlineKeyboardButton(text="🚨 ریپورت/بن",           callback_data="ttype_report")],
            [InlineKeyboardButton(text="🔙 بازگشت",                callback_data="menu_tasks")],
        ])
    )


async def _ask_sessions(cb_or_msg, state, redis):
    names = await get_session_names()
    if not names:
        text = "❌ سشنی وجود ندارد"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 افزودن سشن", callback_data="session_add")]
        ])
    else:
        text = (
            f"📱 <b>سشن‌های موجود ({len(names)} عدد)</b>\n\n"
            "عدد سشن (0=همه):"
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


@router.callback_query(F.data == "ttype_leave")
async def ttype_leave(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="leave")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "🚪 <b>خروج از گروه/کانال</b>\n\n"
        "لینک یا یوزرنیم را بفرستید:\n"
        "مثال: <code>@mychannel</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_add_bot")
async def ttype_add_bot(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="add_bot")
    await state.set_state(NewTaskStates.bot_target)
    await cb.message.edit_text(
        "🤖 <b>اد به بات</b>\n\n"
        "یوزرنیم بات را بفرستید:\n"
        "مثال: <code>@mybot</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.message(NewTaskStates.bot_target)
async def task_bot_target(message: Message, state: FSMContext, redis: Redis):
    await state.update_data(target=message.text.strip())
    await state.set_state(NewTaskStates.count)
    await message.answer("🔢 تعداد سشن برای اد (0=همه):")


@router.callback_query(F.data == "ttype_report")
async def ttype_report(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="report")
    await state.set_state(NewTaskStates.report_target)
    await cb.message.edit_text(
        "🚨 <b>ریپورت/بن</b>\n\n"
        "لینک یا یوزرنیم هدف را بفرستید:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="task_new")]
        ])
    )


@router.message(NewTaskStates.report_target)
async def task_report_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await state.set_state(NewTaskStates.report_reason)
    await message.answer(
        "📝 دلیل ریپورت را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔞 اسپم",               callback_data="rr_spam")],
            [InlineKeyboardButton(text="🚩 محتوای غیرقانونی", callback_data="rr_illegal")],
            [InlineKeyboardButton(text="💀 خشونت/تهدید",  callback_data="rr_violence")],
            [InlineKeyboardButton(text="ℹ️ سایر",                 callback_data="rr_other")],
        ])
    )


@router.callback_query(F.data.startswith("rr_"), NewTaskStates.report_reason)
async def task_report_reason(cb: CallbackQuery, state: FSMContext, redis: Redis):
    reason = cb.data.replace("rr_", "")
    await state.update_data(reason=reason)
    await state.set_state(NewTaskStates.count)
    await cb.message.edit_text("🔢 تعداد سشن برای ریپورت (0=همه):")


@router.message(NewTaskStates.source)
async def task_source(message: Message, state: FSMContext):
    await state.update_data(source=message.text.strip())
    await state.set_state(NewTaskStates.target)
    await message.answer("لینک گروه <b>مقصد</b> را بفرستید:", parse_mode="HTML")


@router.message(NewTaskStates.target)
async def task_target(message: Message, state: FSMContext, redis: Redis):
    await state.update_data(target=message.text.strip())
    await state.set_state(NewTaskStates.count)
    await message.answer("🔢 تعداد سشن (0=همه):")


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
        await message.answer("📱 هر سشن چند نفر اد کند? (5-20):")
    elif data["type"] == "reaction":
        await state.set_state(NewTaskStates.emoji)
        await message.answer("👍 ایموجی ریاکشن را بفرستید:")
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
async def sess_all(cb: CallbackQuery, state: FSMContext, redis: Redis):
    await state.update_data(sessions=0)
    await _submit_task(cb.message, state, redis)


@router.message(NewTaskStates.sessions)
async def task_sessions(message: Message, state: FSMContext, redis: Redis):
    try:
        n = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید")
        return
    await state.update_data(sessions=n)
    await _submit_task(message, state, redis)


async def _submit_task(target, state, redis):
    data = await state.get_data()
    await state.clear()
    task_id = str(uuid.uuid4())[:8]
    task = {
        "id":          task_id,
        "type":        data.get("type"),
        "target":      data.get("target", ""),
        "source":      data.get("source", ""),
        "count":       data.get("count", 0),
        "per_session": data.get("per_session", 10),
        "sessions":    data.get("sessions", 0),
        "emoji":       data.get("emoji", ""),
        "reason":      data.get("reason", ""),
        "status":      "pending",
        "done":        0,
        "failed":      0,
        "created_at":  time.time(),
        "finished_at": 0,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    tasks_list = []
    if os.path.exists(TASK_FILE):
        try:
            tasks_list = json.load(open(TASK_FILE))
        except Exception:
            pass
    tasks_list.append(task)
    with open(TASK_FILE, "w") as f:
        json.dump(tasks_list, f, ensure_ascii=False, indent=2)
    await redis.rpush(TASK_QUEUE, json.dumps(task))
    tp = TYPE_FA.get(task["type"], task["type"])
    sess_text = str(task["sessions"]) if task["sessions"] else "همه"
    text = (
        f"✅ <b>تسک ایجاد شد</b>\n\n"
        f"• نوع: {tp}\n"
        f"• هدف: <code>{task['target']}</code>\n"
        f"• سشن: {sess_text}\n"
        f"• ID: <code>{task_id}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 لیست تسک‌ها", callback_data="task_list")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")],
    ])
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
