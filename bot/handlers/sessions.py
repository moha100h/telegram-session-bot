import os
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from redis.asyncio import Redis
from services.session_manager import (
    get_all_sessions, get_active_sessions,
    add_session, delete_session, get_session,
    verify_session, verify_all_sessions,
    leave_channel, get_session_names
)

router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

ICON_OK   = "\u2705"
ICON_WARN = "\u26a0\ufe0f"
ICON_RED  = "\ud83d\udd34"
ICON_NO   = "\u274c"


class AddSessionStates(StatesGroup):
    phone    = State()
    code     = State()
    password = State()


def is_admin(uid): return uid == ADMIN_ID


def sessions_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u2795 \u0627\u0641\u0632\u0648\u062f\u0646 \u0633\u0634\u0646",           callback_data="session_add")],
        [InlineKeyboardButton(text="\ud83d\udccb \u0644\u06cc\u0633\u062a \u0633\u0634\u0646\u200c\u0647\u0627",       callback_data="session_list")],
        [InlineKeyboardButton(text="\u2705 \u062a\u0633\u062a \u0647\u0645\u0647 \u0633\u0634\u0646\u200c\u0647\u0627",   callback_data="session_verify_all")],
        [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a",            callback_data="menu_main")],
    ])


@router.callback_query(F.data == "menu_sessions")
async def sessions_menu(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    sessions = await get_all_sessions()
    active   = sum(1 for s in sessions if s.get("active"))
    verified = sum(1 for s in sessions if s.get("verified"))
    await cb.message.edit_text(
        "\ud83d\udcf1 <b>\u0645\u062f\u06cc\u0631\u06cc\u062a \u0633\u0634\u0646\u200c\u0647\u0627</b>\n\n"
        "\u2022 \u06a9\u0644: <b>" + str(len(sessions)) + "</b>\n"
        "\u2022 \u0641\u0627\u06cc\u0644 \u0645\u0648\u062c\u0648\u062f: <b>" + str(active) + "</b>\n"
        "\u2022 \u062a\u0633\u062a \u0634\u062f\u0647: <b>" + str(verified) + "</b>",
        reply_markup=sessions_menu_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data == "session_list")
async def session_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    sessions = await get_all_sessions()
    if not sessions:
        await cb.message.edit_text(
            "\ud83d\udced \u0647\u06cc\u0686 \u0633\u0634\u0646\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\u2795 \u0627\u0641\u0632\u0648\u062f\u0646", callback_data="session_add")],
                [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_sessions")],
            ])
        )
        return
    buttons = []
    for s in sessions:
        if s.get("verified"):
            icon = ICON_OK
        elif s.get("active"):
            icon = ICON_WARN
        else:
            icon = ICON_RED
        name  = s.get("fullname") or s.get("phone", s["name"])
        uname = (" @" + s["username"]) if s.get("username") else ""
        buttons.append([InlineKeyboardButton(
            text=icon + " " + name + uname,
            callback_data="session_info_" + s["name"]
        )])
    buttons.append([InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="menu_sessions")])
    await cb.message.edit_text(
        "\ud83d\udcf1 <b>\u0633\u0634\u0646\u200c\u0647\u0627 (" + str(len(sessions)) + " \u0639\u062f\u062f)</b>\n"
        + ICON_OK + "=\u062a\u0633\u062a\u0634\u062f\u0647  " + ICON_WARN + "=\u062a\u0633\u062a\u0646\u0634\u062f\u0647  " + ICON_RED + "=\u0641\u0627\u06cc\u0644 \u0646\u062f\u0627\u0631\u062f",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("session_info_"))
async def session_info(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_info_", "")
    s = await get_session(name)
    if not s:
        await cb.answer("\u0633\u0634\u0646 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f", show_alert=True)
        return
    icon      = ICON_OK   if s.get("verified") else (ICON_WARN if s.get("active") else ICON_RED)
    file_icon = ICON_OK   if s.get("active")   else ICON_NO
    test_icon = ICON_OK   if s.get("verified") else ICON_WARN
    test_lbl  = "\u0645\u0639\u062a\u0628\u0631" if s.get("verified") else "\u062a\u0633\u062a \u0646\u0634\u062f\u0647"
    lines = [icon + " <b>" + (s.get("fullname") or s.get("phone", name)) + "</b>"]
    lines.append("\u2022 \u0634\u0645\u0627\u0631\u0647: <code>" + s.get("phone", "") + "</code>")
    if s.get("username"):
        lines.append("\u2022 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645: @" + s["username"])
    if s.get("user_id"):
        lines.append("\u2022 ID: <code>" + str(s["user_id"]) + "</code>")
    lines.append("\u2022 \u0641\u0627\u06cc\u0644: " + file_icon)
    lines.append("\u2022 \u062a\u0633\u062a: " + test_icon + " " + test_lbl)
    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udd0d \u062a\u0633\u062a \u0633\u0634\u0646",  callback_data="session_verify_" + name)],
            [InlineKeyboardButton(text="\ud83d\uddd1 \u062d\u0630\u0641 \u0633\u0634\u0646",  callback_data="session_del_" + name)],
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a",     callback_data="session_list")],
        ])
    )


@router.callback_query(F.data.startswith("session_verify_"))
async def session_verify_one(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_verify_", "")
    await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062a\u0633\u062a \u0633\u0634\u0646...")
    result = await verify_session(name)
    if result["ok"]:
        me = result["me"]
        await cb.message.edit_text(
            ICON_OK + " <b>\u0633\u0634\u0646 \u0645\u0639\u062a\u0628\u0631 \u0627\u0633\u062a</b>\n\n"
            "\u2022 \u0646\u0627\u0645: " + me["fullname"] + "\n"
            "\u2022 \u0634\u0645\u0627\u0631\u0647: <code>" + me["phone"] + "</code>\n"
            "\u2022 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645: @" + (me["username"] or "-"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="session_info_" + name)]
            ])
        )
    else:
        await cb.message.edit_text(
            ICON_NO + " <b>\u0633\u0634\u0646 \u0646\u0627\u0645\u0639\u062a\u0628\u0631</b>\n\u062e\u0637\u0627: " + str(result.get("error", "")),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\ud83d\uddd1 \u062d\u0630\u0641",      callback_data="session_del_" + name)],
                [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="session_list")],
            ])
        )


@router.callback_query(F.data == "session_verify_all")
async def session_verify_all(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    names = await get_session_names()
    if not names:
        await cb.answer("\u0647\u06cc\u0686 \u0633\u0634\u0646\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f", show_alert=True)
        return
    await cb.message.edit_text("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062a\u0633\u062a " + str(len(names)) + " \u0633\u0634\u0646...")
    results    = await verify_all_sessions()
    ok_count   = len(results["ok"])
    fail_count = len(results["fail"])
    text = (
        "\ud83d\udd0d <b>\u0646\u062a\u06cc\u062c\u0647 \u062a\u0633\u062a \u0633\u0634\u0646\u200c\u0647\u0627</b>\n\n"
        + ICON_OK + " \u0645\u0639\u062a\u0628\u0631: <b>" + str(ok_count) + "</b>\n"
        + ICON_NO + " \u0646\u0627\u0645\u0639\u062a\u0628\u0631: <b>" + str(fail_count) + "</b>"
    )
    if results["fail"]:
        fail_lines = [ICON_NO + " " + f["name"] + ": " + str(f["error"]) for f in results["fail"]]
        text += "\n\n" + "\n".join(fail_lines)
    await cb.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udccb \u0644\u06cc\u0633\u062a \u0633\u0634\u0646\u200c\u0647\u0627", callback_data="session_list")],
            [InlineKeyboardButton(text="\ud83d\udd19 \u0628\u0627\u0632\u06af\u0634\u062a",     callback_data="menu_sessions")],
        ])
    )


@router.callback_query(F.data.startswith("session_del_"))
async def session_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("session_del_", "")
    await delete_session(name)
    await cb.answer("\u2705 \u0633\u0634\u0646 \u062d\u0630\u0641 \u0634\u062f")
    await session_list(cb)


@router.callback_query(F.data.startswith("sc_retest_"))
async def sc_retest(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("sc_retest_", "")
    await cb.message.answer("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u062a\u0633\u062a \u0633\u0634\u0646 " + name + "...")
    result = await verify_session(name)
    if result["ok"]:
        me = result["me"]
        await cb.message.answer(
            ICON_OK + " <b>\u0633\u0634\u0646 \u0645\u0639\u062a\u0628\u0631 \u0634\u062f</b>\n"
            "\u2022 \u0646\u0627\u0645: " + me["fullname"] + "\n"
            "\u2022 \u0634\u0645\u0627\u0631\u0647: <code>" + me["phone"] + "</code>",
            parse_mode="HTML"
        )
    else:
        await cb.message.answer(
            ICON_NO + " \u0633\u0634\u0646 \u0647\u0646\u0648\u0632 \u0646\u0627\u0645\u0639\u062a\u0628\u0631: " + str(result.get("error")),
            parse_mode="HTML"
        )
    await cb.answer()


@router.callback_query(F.data.startswith("sc_delete_"))
async def sc_delete(cb: CallbackQuery):
    if not is_admin(cb.from_user.id): return
    name = cb.data.replace("sc_delete_", "")
    await delete_session(name)
    await cb.answer("\u2705 \u0633\u0634\u0646 \u062d\u0630\u0641 \u0634\u062f", show_alert=True)
    await cb.message.answer("\ud83d\uddd1 \u0633\u0634\u0646 <code>" + name + "</code> \u062d\u0630\u0641 \u0634\u062f.", parse_mode="HTML")


@router.callback_query(F.data == "session_add")
async def session_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await state.clear()
    await state.set_state(AddSessionStates.phone)
    await cb.message.edit_text(
        "\u2795 <b>\u0627\u0641\u0632\u0648\u062f\u0646 \u0633\u0634\u0646 \u062c\u062f\u06cc\u062f</b>\n\n"
        "\ud83d\udcf1 \u0634\u0645\u0627\u0631\u0647 \u062a\u0644\u06af\u0631\u0627\u0645 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a\u06cc\u062f:\n"
        "\u0645\u062b\u0627\u0644: <code>+989123456789</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u274c \u0644\u063a\u0648", callback_data="menu_sessions")]
        ])
    )


@router.message(AddSessionStates.phone)
async def session_add_phone(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    phone = message.text.strip()
    await message.answer("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u0627\u0631\u0633\u0627\u0644 \u06a9\u062f...")
    result = await add_session(redis, phone, step="send_code")
    if not result.get("ok"):
        await message.answer("\u274c \u062e\u0637\u0627: " + result.get("error", "unknown"))
        await state.clear()
        return
    await state.update_data(phone=phone, phone_code_hash=result["phone_code_hash"])
    await state.set_state(AddSessionStates.code)
    await message.answer(
        "\u2705 \u06a9\u062f \u0627\u0631\u0633\u0627\u0644 \u0634\u062f\n"
        "\ud83d\udd22 \u06a9\u062f \u062f\u0631\u06cc\u0627\u0641\u062a\u06cc \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f (\u0641\u0642\u0637 \u0627\u0631\u0642\u0627\u0645):"
    )


@router.message(AddSessionStates.code)
async def session_add_code(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    code = message.text.strip()
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="sign_in",
                               code=code, phone_code_hash=data.get("phone_code_hash"))
    if result.get("need_password"):
        await state.set_state(AddSessionStates.password)
        await message.answer("\ud83d\udd10 \u0631\u0645\u0632 2FA \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:")
        return
    if not result["ok"]:
        await message.answer("\u274c \u062e\u0637\u0627: " + result.get("error", "unknown"))
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "\u2705 <b>\u0633\u0634\u0646 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0627\u0636\u0627\u0641\u0647 \u0634\u062f!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udcf1 \u0644\u06cc\u0633\u062a \u0633\u0634\u0646\u200c\u0647\u0627", callback_data="session_list")]
        ])
    )


@router.message(AddSessionStates.password)
async def session_add_password(message: Message, state: FSMContext, redis: Redis):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    result = await add_session(redis, data["phone"], step="2fa", password=message.text.strip())
    if not result["ok"]:
        await message.answer("\u274c \u062e\u0637\u0627: " + result.get("error", "unknown"))
        await state.clear()
        return
    await state.clear()
    await message.answer(
        "\u2705 <b>\u0633\u0634\u0646 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0627\u0636\u0627\u0641\u0647 \u0634\u062f!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\ud83d\udcf1 \u0644\u06cc\u0633\u062a \u0633\u0634\u0646\u200c\u0647\u0627", callback_data="session_list")]
        ])
    )
