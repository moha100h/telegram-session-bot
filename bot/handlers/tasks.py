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


class JoinStates(StatesGroup):
    target = State()
    count = State()


class G2GStates(StatesGroup):
    source = State()
    dest = State()
    count = State()
    per_session = State()


class ViewStates(StatesGroup):
    target = State()
    count = State()


class ReactionStates(StatesGroup):
    target = State()
    emoji = State()
    count = State()


class CancelStates(StatesGroup):
    task_id = State()


def back_btn(cb="menu_tasks"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]
    ])


def tasks_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 عضویت در کانال/گروه", callback_data="task_join")],
        [InlineKeyboardButton(text="🔄 گروه به گروه", callback_data="task_g2g")],
        [InlineKeyboardButton(text="👁 ویو پست", callback_data="task_view")],
        [InlineKeyboardButton(text="👍 ریاکشن", callback_data="task_reaction")],
        [InlineKeyboardButton(text="📋 لیست تسک‌ها", callback_data="task_list"),
         InlineKeyboardButton(text="❌ لغو تسک", callback_data="task_cancel_menu")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_tasks")
async def tasks_menu_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    tasks = await get_all_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    pending = sum(1 for t in tasks if t["status"] == "pending")
    done = sum(1 for t in tasks if t["status"] == "completed")
    await cb.message.edit_text(
        f"⚙️ <b>مدیریت تسک‌ها</b>\n\n"
        f"▶️ در حال اجرا: <b>{running}</b>\n"
        f"⏳ در صف: <b>{pending}</b>\n"
        f"✅ تمام شده: <b>{done}</b>",
        reply_markup=tasks_menu(), parse_mode="HTML")


# ────────────────────────────────────────────────────────────────
# JOIN
# ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "task_join")
async def task_join_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "📥 <b>تسک عضویت</b>\n\nلینک یا یوزرنیم کانال/گروه مقصد:\n"
        "مثال: @channel یا https://t.me/channel",
        parse_mode="HTML", reply_markup=back_btn())
    await state.set_state(JoinStates.target)


@router.message(JoinStates.target)
async def task_join_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    sessions = await get_active_sessions()
    await message.answer(
        f"📊 سشن فعال: <b>{len(sessions)}</b>\nچند سشن عضو شوند? (0 = همه)",
        parse_mode="HTML", reply_markup=back_btn())
    await state.set_state(JoinStates.count)


@router.message(JoinStates.count)
async def task_join_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید", reply_markup=back_btn())
        return
    data = await state.get_data()
    await state.clear()
    sessions = await get_active_sessions()
    use = sessions[:count] if count > 0 else sessions
    tid = await create_task(redis, {
        "type": "join",
        "target": data["target"],
        "sessions": [s["name"] for s in use],
        "total": len(use),
    })
    await message.answer(
        f"✅ تسک عضویت ساخته شد\n"
        f"🆔 ID: <code>{tid}</code>\n"
        f"📱 سشن: {len(use)}\n"
        f"🎯 مقصد: {data['target']}",
        parse_mode="HTML", reply_markup=tasks_menu())


# ────────────────────────────────────────────────────────────────
# GROUP TO GROUP
# ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "task_g2g")
async def task_g2g_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "🔄 <b>گروه به گروه</b>\n\n"
        "آیدی گروه <b>مبدا</b> را بفرستید:\n"
        "مثال: @groupname یا https://t.me/groupname یا -100123456789",
        parse_mode="HTML", reply_markup=back_btn())
    await state.set_state(G2GStates.source)


@router.message(G2GStates.source)
async def task_g2g_source(message: Message, state: FSMContext):
    await state.update_data(source=message.text.strip())
    await message.answer(
        "🎯 آیدی گروه <b>مقصد</b> را بفرستید:\n"
        "مثال: @groupname یا https://t.me/groupname",
        parse_mode="HTML", reply_markup=back_btn())
    await state.set_state(G2GStates.dest)


@router.message(G2GStates.dest)
async def task_g2g_dest(message: Message, state: FSMContext):
    await state.update_data(dest=message.text.strip())
    await message.answer(
        "📊 تعداد کل کاربر برای انتقال:",
        reply_markup=back_btn())
    await state.set_state(G2GStates.count)


@router.message(G2GStates.count)
async def task_g2g_count(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید", reply_markup=back_btn())
        return
    await state.update_data(count=count)
    await message.answer(
        "📱 هر سشن چند نفر اد کند?\n"
        "پیشنهاد: 10 تا 50 نفر",
        reply_markup=back_btn())
    await state.set_state(G2GStates.per_session)


@router.message(G2GStates.per_session)
async def task_g2g_per_session(message: Message, state: FSMContext, redis: Redis):
    try:
        per = max(1, min(50, int(message.text.strip())))
    except ValueError:
        per = 20
    data = await state.get_data()
    await state.clear()
    sessions = await get_active_sessions()
    if not sessions:
        await message.answer("❌ هیچ سشن فعالی وجود ندارد", reply_markup=tasks_menu())
        return
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
        f"✅ تسک گروه به گروه ساخته شد\n"
        f"🆔 ID: <code>{tid}</code>\n"
        f"📊 تعداد: {data['count']} نفر\n"
        f"📱 هر سشن: {per} نفر\n"
        f"📤 مبدا: {data['source']}\n"
        f"📥 مقصد: {data['dest']}",
        parse_mode="HTML", reply_markup=tasks_menu())


# ────────────────────────────────────────────────────────────────
# VIEW
# ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "task_view")
async def task_view_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "👁 <b>ویو پست</b>\n\nلینک پست را بفرستید:\n"
        "مثال: https://t.me/channel/123",
        parse_mode="HTML", reply_markup=back_btn())
    await state.set_state(ViewStates.target)


@router.message(ViewStates.target)
async def task_view_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await message.answer("📊 تعداد ویو:", reply_markup=back_btn())
    await state.set_state(ViewStates.count)


@router.message(ViewStates.count)
async def task_view_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید", reply_markup=back_btn())
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


# ────────────────────────────────────────────────────────────────
# REACTION
# ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "task_reaction")
async def task_reaction_start(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        "👍 <b>ریاکشن</b>\n\nلینک پست را بفرستید:\n"
        "مثال: https://t.me/channel/123",
        parse_mode="HTML", reply_markup=back_btn())
    await state.set_state(ReactionStates.target)


@router.message(ReactionStates.target)
async def task_reaction_target(message: Message, state: FSMContext):
    await state.update_data(target=message.text.strip())
    await message.answer(
        "😊 ایموجی ریاکشن:\n"
        "👍 ❤️ 🔥 🎉 👏 🤔 😮 😢 😡",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👍", callback_data="react_👍"),
             InlineKeyboardButton(text="❤️", callback_data="react_❤️"),
             InlineKeyboardButton(text="🔥", callback_data="react_🔥"),
             InlineKeyboardButton(text="🎉", callback_data="react_🎉")],
            [InlineKeyboardButton(text="👏", callback_data="react_👏"),
             InlineKeyboardButton(text="🤔", callback_data="react_🤔"),
             InlineKeyboardButton(text="😮", callback_data="react_😮"),
             InlineKeyboardButton(text="😢", callback_data="react_😢")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")],
        ]))
    await state.set_state(ReactionStates.emoji)


@router.callback_query(F.data.startswith("react_"), ReactionStates.emoji)
async def task_reaction_emoji_cb(cb: CallbackQuery, state: FSMContext):
    emoji = cb.data.replace("react_", "")
    await state.update_data(emoji=emoji)
    await cb.message.edit_text(
        f"ایموجی انتخاب شد: {emoji}\n📊 تعداد ریاکشن:",
        reply_markup=back_btn())
    await state.set_state(ReactionStates.count)


@router.message(ReactionStates.count)
async def task_reaction_count(message: Message, state: FSMContext, redis: Redis):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("❌ عدد صحیح وارد کنید", reply_markup=back_btn())
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


# ────────────────────────────────────────────────────────────────
# LIST & CANCEL
# ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "task_list")
async def task_list(cb: CallbackQuery):
    tasks = await get_all_tasks()
    if not tasks:
        await cb.message.edit_text("📭 هیچ تسکی وجود ندارد", reply_markup=back_btn())
        return
    icons = {"pending": "⏳", "running": "▶️", "completed": "✅", "failed": "❌", "cancelled": "🚫"}
    tnames = {"join": "عضویت", "group2group": "گروه→گروه", "view": "ویو", "reaction": "ریاکشن"}
    text = "📋 <b>لیست تسک‌ها:</b>\n\n"
    for t in list(reversed(tasks))[:15]:
        icon = icons.get(t["status"], "?")
        tname = tnames.get(t["type"], t["type"])
        text += f"{icon} <code>{t['id']}</code> | {tname} | {t.get('done',0)}/{t.get('total',0)}\n"
    await cb.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="task_list")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")],
        ]))


@router.callback_query(F.data == "task_cancel_menu")
async def task_cancel_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    tasks = await get_all_tasks()
    active = [t for t in tasks if t["status"] in ("pending", "running")]
    if not active:
        await cb.message.edit_text("❌ تسک فعالی وجود ندارد", reply_markup=back_btn())
        return
    buttons = []
    tnames = {"join": "عضویت", "group2group": "گروه→گروه", "view": "ویو", "reaction": "ریاکشن"}
    for t in active:
        tname = tnames.get(t["type"], t["type"])
        buttons.append([InlineKeyboardButton(
            text=f"❌ {t['id']} | {tname} | {t.get('done',0)}/{t.get('total',0)}",
            callback_data=f"cancel_task_{t['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_tasks")])
    await cb.message.edit_text("❌ تسک مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("cancel_task_"))
async def task_cancel_do(cb: CallbackQuery, redis: Redis):
    tid = cb.data.replace("cancel_task_", "")
    await cancel_task(redis, tid)
    await cb.answer(f"✅ تسک {tid} لغو شد")
    await task_cancel_menu(cb, FSMContext.__new__(FSMContext))
    # refresh list
    tasks = await get_all_tasks()
    active = [t for t in tasks if t["status"] in ("pending", "running")]
    if not active:
        await cb.message.edit_text(f"✅ تسک <code>{tid}</code> لغو شد",
            parse_mode="HTML", reply_markup=back_btn())
    else:
        await task_cancel_menu(cb, None)
