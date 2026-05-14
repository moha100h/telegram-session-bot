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
    "join":        "\u0639\u0636\u0648\u06cc\u062a",
    "group2group": "\u06af\u0631\u0648\u0647\u2192\u06af\u0631\u0648\u0647",
    "view":        "\u0648\u06cc\u0648",
    "reaction":    "\u0631\u06cc\u0627\u06a9\u0634\u0646",
    "leave":       "\u062e\u0631\u0648\u062c",
    "add_bot":     "\u0627\u062f \u0628\u0627\u062a",
    "report":      "\u0631\u06cc\u067e\u0648\u0631\u062a",
}

STATUS_ICON = {
    "running":   "\u25b6\ufe0f",
    "pending":   "\u23f3",
    "completed": "\u2705",
    "failed":    "\u274c",
    "cancelled": "\u26d4",
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
        [InlineKeyboardButton(text="\u2795 \u062a\u0633\u06a9 \u062c\u062f\u06cc\u062f",      callback_data="task_new")],
        [InlineKeyboardButton(text="\ud83d\udccb \u0644\u06cc\u0633\u062a \u062a\u0633\u06a9\u200c\u0647\u0627", callback_data="task_list")],
        [InlineKeyboardButton(text="\ud83d\udcca \u0622\u0645\u0627\u0631 \u0627\u0645\u0631\u0648\u0632",  callback_data="task_daily_stats")],
        [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a",         callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_tasks")
async def tasks_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _cleanup_old_tasks()
    tasks = await get_all_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    pending = sum(1 for t in tasks if t["status"] == "pending")
    await cb.message.edit_text(
        "\u2699\ufe0f <b>\u0645\u062f\u06cc\u0631\u06cc\u062a \u062a\u0633\u06a9\u200c\u0647\u0627</b>\n\n"
        "\u25b6\ufe0f \u062f\u0631 \u062d\u0627\u0644: <b>" + str(running) + "</b>\n"
        "\u23f3 \u062f\u0631 \u0635\u0641: <b>" + str(pending) + "</b>\n"
        "\ud83d\udccb \u06a9\u0644: <b>" + str(len(tasks)) + "</b>",
        parse_mode="HTML",
        reply_markup=tasks_menu_kb()
    )


@router.callback_query(F.data == "task_daily_stats")
async def task_daily_stats(cb: CallbackQuery):
    stats = _load_stats()
    key = _today_key()
    today = stats.get(key, {})
    if not today:
        text = "\ud83d\udcca <b>\u0622\u0645\u0627\u0631 \u0627\u0645\u0631\u0648\u0632</b>\n\n\u0647\u06cc\u0686 \u062a\u0633\u06a9\u06cc \u0627\u0645\u0631\u0648\u0632 \u0627\u0646\u062c\u0627\u0645 \u0646\u0634\u062f\u0647"
    else:
        lines = ["\ud83d\udcca <b>\u0622\u0645\u0627\u0631 \u0627\u0645\u0631\u0648\u0632 (" + key + ")</b>\n"]
        for tp, vals in today.items():
            name = TYPE_FA.get(tp, tp)
            lines.append("\u2022 " + name + ": \u2705" + str(vals.get("done", 0)) + " | \u274c" + str(vals.get("failed", 0)))
        text = "\n".join(lines)
    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_tasks")]
        ])
    )


@router.callback_query(F.data == "task_list")
async def task_list(cb: CallbackQuery):
    await _cleanup_old_tasks()
    tasks = await get_all_tasks()
    if not tasks:
        await cb.message.edit_text(
            "\ud83d\udced \u0647\u06cc\u0686 \u062a\u0633\u06a9\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_tasks")]
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
            text=icon + " " + tp + " | " + str(done) + "/" + str(total),
            callback_data="task_info_" + t["id"]
        )])
    buttons.append([InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_tasks")])
    await cb.message.edit_text(
        "\ud83d\udccb <b>\u0644\u06cc\u0633\u062a \u062a\u0633\u06a9\u200c\u0647\u0627 (" + str(len(tasks)) + " \u0639\u062f\u062f)</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("task_info_"))
async def task_info(cb: CallbackQuery):
    tid  = cb.data.replace("task_info_", "")
    task = await get_task(tid)
    if not task:
        await cb.answer("\u062a\u0633\u06a9 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f", show_alert=True)
        return
    tp     = TYPE_FA.get(task["type"], task["type"])
    done   = task.get("done", 0)
    fail   = task.get("failed", 0)
    total  = task.get("count", "?")
    status = task.get("status", "?")
    target = task.get("target", "-")
    kb = []
    if status in ("running", "pending"):
        kb.append([InlineKeyboardButton(text="\u23f9 \u0644\u063a\u0648 \u062a\u0633\u06a9", callback_data="task_cancel_" + tid)])
    kb.append([InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_list")])
    await cb.message.edit_text(
        "\u2139\ufe0f <b>\u062c\u0632\u0626\u06cc\u0627\u062a \u062a\u0633\u06a9</b>\n\n"
        "\u2022 \u0646\u0648\u0639: " + tp + "\n"
        "\u2022 \u0647\u062f\u0641: <code>" + str(target) + "</code>\n"
        "\u2022 \u0648\u0636\u0639\u06cc\u062a: " + status + "\n"
        "\u2022 \u0645\u0648\u0641\u0642: <b>" + str(done) + "</b> | \u0646\u0627\u0645\u0648\u0641\u0642: <b>" + str(fail) + "</b> | \u06a9\u0644: <b>" + str(total) + "</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("task_cancel_"))
async def task_cancel(cb: CallbackQuery):
    tid = cb.data.replace("task_cancel_", "")
    await cancel_task(tid)
    await cb.answer("\u2705 \u062a\u0633\u06a9 \u0644\u063a\u0648 \u0634\u062f")
    await task_list(cb)


@router.callback_query(F.data == "task_new")
async def task_new(cb: CallbackQuery, state: FSMContext):
    await state.set_state(NewTaskStates.type_sel)
    await cb.message.edit_text(
        "\u2795 <b>\u0646\u0648\u0639 \u062a\u0633\u06a9 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udcf1 \u0639\u0636\u0648\u06cc\u062a \u06af\u0631\u0648\u0647/\u06a9\u0627\u0646\u0627\u0644", callback_data="ttype_join")],
            [InlineKeyboardButton(text="\ud83d\udd04 \u06af\u0631\u0648\u0647 \u0628\u0647 \u06af\u0631\u0648\u0647",       callback_data="ttype_g2g")],
            [InlineKeyboardButton(text="\ud83d\udc41 \u0648\u06cc\u0648 \u067e\u0633\u062a",             callback_data="ttype_view")],
            [InlineKeyboardButton(text="\ud83d\udc4d \u0631\u06cc\u0627\u06a9\u0634\u0646",                callback_data="ttype_reaction")],
            [InlineKeyboardButton(text="\ud83d\udeaa \u062e\u0631\u0648\u062c \u0627\u0632 \u06af\u0631\u0648\u0647/\u06a9\u0627\u0646\u0627\u0644", callback_data="ttype_leave")],
            [InlineKeyboardButton(text="\ud83e\udd16 \u0627\u062f \u0628\u0647 \u0628\u0627\u062a",        callback_data="ttype_add_bot")],
            [InlineKeyboardButton(text="\ud83d\udea8 \u0631\u06cc\u067e\u0648\u0631\u062a/\u0628\u0646",           callback_data="ttype_report")],
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a",                callback_data="menu_tasks")],
        ])
    )


async def _ask_sessions(cb_or_msg, state, redis):
    names = await get_session_names()
    if not names:
        text = "\u274c \u0633\u0634\u0646\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udcf1 \u0627\u0641\u0632\u0648\u062f\u0646 \u0633\u0634\u0646", callback_data="session_add")]
        ])
    else:
        text = (
            "\ud83d\udcf1 <b>\u0633\u0634\u0646\u200c\u0647\u0627\u06cc \u0645\u0648\u062c\u0648\u062f (" + str(len(names)) + " \u0639\u062f\u062f)</b>\n\n"
            "\u0639\u062f\u062f \u0633\u0634\u0646 (0=\u0647\u0645\u0647):"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u0647\u0645\u0647 \u0633\u0634\u0646\u200c\u0647\u0627", callback_data="sess_all")]
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
        "\ud83d\udcf1 <b>\u0639\u0636\u0648\u06cc\u062a</b>\n\n\u0644\u06cc\u0646\u06a9 \u06af\u0631\u0648\u0647/\u06a9\u0627\u0646\u0627\u0644 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_g2g")
async def ttype_g2g(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="group2group")
    await state.set_state(NewTaskStates.source)
    await cb.message.edit_text(
        "\ud83d\udd04 <b>\u06af\u0631\u0648\u0647 \u0628\u0647 \u06af\u0631\u0648\u0647</b>\n\n\u0644\u06cc\u0646\u06a9 \u06af\u0631\u0648\u0647 <b>\u0645\u0628\u062f\u0627</b> \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_view")
async def ttype_view(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="view")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "\ud83d\udc41 <b>\u0648\u06cc\u0648 \u067e\u0633\u062a</b>\n\n\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_reaction")
async def ttype_reaction(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="reaction")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "\ud83d\udc4d <b>\u0631\u06cc\u0627\u06a9\u0634\u0646</b>\n\n\u0644\u06cc\u0646\u06a9 \u067e\u0633\u062a \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_leave")
async def ttype_leave(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="leave")
    await state.set_state(NewTaskStates.target)
    await cb.message.edit_text(
        "\ud83d\udeaa <b>\u062e\u0631\u0648\u062c \u0627\u0632 \u06af\u0631\u0648\u0647/\u06a9\u0627\u0646\u0627\u0644</b>\n\n"
        "\u0644\u06cc\u0646\u06a9 \u06cc\u0627 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:\n"
        "\u0645\u062b\u0627\u0644: <code>@mychannel</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.callback_query(F.data == "ttype_add_bot")
async def ttype_add_bot(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="add_bot")
    await state.set_state(NewTaskStates.bot_target)
    await cb.message.edit_text(
        "\ud83e\udd16 <b>\u0627\u062f \u0628\u0647 \u0628\u0627\u062a</b>\n\n"
        "\u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u0628\u0627\u062a \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:\n"
        "\u0645\u062b\u0627\u0644: <code>@mybot</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.message(NewTaskStates.bot_target)
async def task_bot_target(message: Message, state: FSMContext, redis: Redis):
    await state.update_data(target=message.text.strip())
    await state.set_state(NewTaskStates.count)
    await message.answer("\ud83d\udd22 \u062a\u0639\u062f\u0627\u062f \u0633\u0634\u0646 \u0628\u0631\u0627\u06cc \u0627\u062f (0=\u0647\u0645\u0647):")


@router.callback_query(F.data == "ttype_report")
async def ttype_report(cb: CallbackQuery, state: FSMContext):
    await state.update_data(type="report")
    await state.set_state(NewTaskStates.report_target)
    await cb.message.edit_text(
        "\ud83d\udea8 <b>\u0631\u06cc\u067e\u0648\u0631\u062a/\u0628\u0646</b>\n\n"
        "\u0644\u06cc\u0646\u06a9 \u06cc\u0627 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u0647\u062f\u0641 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="task_new")]
        ])
    )


@router.message(NewTaskStates.report_target)
async def task_report_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await state.set_state(NewTaskStates.report_reason)
    await message.answer(
        "\ud83d\udcdd \u062f\u0644\u06cc\u0644 \u0631\u06cc\u067e\u0648\u0631\u062a \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd1e \u0627\u0633\u067e\u0645",               callback_data="rr_spam")],
            [InlineKeyboardButton(text="\ud83d\udea9 \u0645\u062d\u062a\u0648\u0627\u06cc \u063a\u06cc\u0631\u0642\u0627\u0646\u0648\u0646\u06cc", callback_data="rr_illegal")],
            [InlineKeyboardButton(text="\ud83d\udc80 \u062e\u0634\u0648\u0646\u062a/\u062a\u0647\u062f\u06cc\u062f",  callback_data="rr_violence")],
            [InlineKeyboardButton(text="\u2139\ufe0f \u0633\u0627\u06cc\u0631",                 callback_data="rr_other")],
        ])
    )


@router.callback_query(F.data.startswith("rr_"), NewTaskStates.report_reason)
async def task_report_reason(cb: CallbackQuery, state: FSMContext, redis: Redis):
    reason = cb.data.replace("rr_", "")
    await state.update_data(reason=reason)
    await state.set_state(NewTaskStates.count)
    await cb.message.edit_text("\ud83d\udd22 \u062a\u0639\u062f\u0627\u062f \u0633\u0634\u0646 \u0628\u0631\u0627\u06cc \u0631\u06cc\u067e\u0648\u0631\u062a (0=\u0647\u0645\u0647):")


@router.message(NewTaskStates.source)
async def task_source(message: Message, state: FSMContext):
    await state.update_data(source=message.text.strip())
    await state.set_state(NewTaskStates.target)
    await message.answer("\u0644\u06cc\u0646\u06a9 \u06af\u0631\u0648\u0647 <b>\u0645\u0642\u0635\u062f</b> \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:", parse_mode="HTML")


@router.message(NewTaskStates.target)
async def task_target(message: Message, state: FSMContext, redis: Redis):
    await state.update_data(target=message.text.strip())
    await state.set_state(NewTaskStates.count)
    await message.answer("\ud83d\udd22 \u062a\u0639\u062f\u0627\u062f \u0633\u0634\u0646 (0=\u0647\u0645\u0647):")


@router.message(NewTaskStates.count)
async def task_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f")
        return
    await state.update_data(count=count)
    data = await state.get_data()
    if data["type"] == "group2group":
        await state.set_state(NewTaskStates.per_session)
        await message.answer("\ud83d\udcf1 \u0647\u0631 \u0633\u0634\u0646 \u0686\u0646\u062f \u0646\u0641\u0631 \u0627\u062f \u06a9\u0646\u062f? (5-20):")
    elif data["type"] == "reaction":
        await state.set_state(NewTaskStates.emoji)
        await message.answer("\ud83d\udc4d \u0627\u06cc\u0645\u0648\u062c\u06cc \u0631\u06cc\u0627\u06a9\u0634\u0646 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:")
    else:
        await _ask_sessions(message, state, redis)


@router.message(NewTaskStates.per_session)
async def task_per_session(message: Message, state: FSMContext, redis: Redis):
    try:
        per = int(message.text.strip())
    except ValueError:
        await message.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f")
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
        await message.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f")
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
    tasks = []
    if os.path.exists(TASK_FILE):
        try:
            tasks = json.load(open(TASK_FILE))
        except Exception:
            pass
    tasks.append(task)
    with open(TASK_FILE, "w") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    await redis.rpush(TASK_QUEUE, json.dumps(task))
    tp = TYPE_FA.get(task["type"], task["type"])
    sess_text = str(task["sessions"]) if task["sessions"] else "\u0647\u0645\u0647"
    text = (
        "\u2705 <b>\u062a\u0633\u06a9 \u0627\u06cc\u062c\u0627\u062f \u0634\u062f</b>\n\n"
        "\u2022 \u0646\u0648\u0639: " + tp + "\n"
        "\u2022 \u0647\u062f\u0641: <code>" + str(task["target"]) + "</code>\n"
        "\u2022 \u0633\u0634\u0646: " + sess_text + "\n"
        "\u2022 ID: <code>" + task_id + "</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\ud83d\udccb \u0644\u06cc\u0633\u062a \u062a\u0633\u06a9\u200c\u0647\u0627", callback_data="task_list")],
        [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_tasks")],
    ])
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
