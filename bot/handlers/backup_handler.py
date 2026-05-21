"""Backup admin panel handler."""
import logging, os
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery, Message, Document,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from db.database import AsyncSessionLocal
from services.settings_service import get_setting as gs, set_setting as ss
from services.backup_service import create_backup, send_backup_to_group, restore_from_zip

logger = logging.getLogger("backup_handler")
router = Router()
SUPERADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


class BackupState(StatesGroup):
    waiting_group_id      = State()
    waiting_interval      = State()
    waiting_restore_file  = State()
    waiting_forward_msg   = State()


def _sa(uid): return uid == SUPERADMIN_ID


# ── صفحه اصلی ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup")
async def adm_backup(cb: CallbackQuery):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f \u0641\u0642\u0637 \u0633\u0648\u067e\u0631\u0627\u062f\u0645\u06cc\u0646", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        group_id = await gs(session, "backup_group_id",       "\u062a\u0646\u0638\u06cc\u0645 \u0646\u0634\u062f\u0647")
        interval = await gs(session, "backup_interval_hours", "1")
        auto_on  = await gs(session, "backup_auto_enabled",   "1")
        last_at  = await gs(session, "backup_last_at",        "\u0647\u0631\u06af\u0632")
    status = "\U0001f7e2 \u0641\u0639\u0627\u0644" if auto_on == "1" else "\U0001f534 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644"
    toggle = "\U0001f534 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u06a9\u0631\u062f\u0646" if auto_on == "1" else "\U0001f7e2 \u0641\u0639\u0627\u0644 \u06a9\u0631\u062f\u0646"
    g_display = f"<code>{group_id}</code>" if group_id != "\u062a\u0646\u0638\u06cc\u0645 \u0646\u0634\u062f\u0647" else "\u274c \u062a\u0646\u0638\u06cc\u0645 \u0646\u0634\u062f\u0647"
    await cb.message.edit_text(
        f"\U0001f5c4 <b>\u0633\u06cc\u0633\u062a\u0645 \u0628\u06a9\u0627\u067e \u062d\u0631\u0641\u0647\u200c\u0627\u06cc</b>\n\n"
        f"\U0001f4cc \u06af\u0631\u0648\u0647 \u062f\u0631\u06cc\u0627\u0641\u062a: {g_display}\n"
        f"\u23f1 \u0641\u0627\u0635\u0644\u0647 \u0628\u06a9\u0627\u067e: <b>\u0647\u0631 {interval} \u0633\u0627\u0639\u062a</b>\n"
        f"\U0001f504 \u0628\u06a9\u0627\u067e \u062e\u0648\u062f\u06a9\u0627\u0631: <b>{status}</b>\n"
        f"\U0001f550 \u0622\u062e\u0631\u06cc\u0646 \u0628\u06a9\u0627\u067e: <b>{last_at}</b>\n\n"
        f"<i>\u26a0\ufe0f \u0628\u0627\u062a \u0628\u0627\u06cc\u062f \u0639\u0636\u0648 \u0648 \u0627\u062f\u0645\u06cc\u0646 \u06af\u0631\u0648\u0647 \u0628\u0627\u0634\u062f.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4e4 \u0628\u06a9\u0627\u067e \u0641\u0648\u0631\u06cc",         callback_data="adm_backup_now")],
            [InlineKeyboardButton(text="\u267b\ufe0f \u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc",   callback_data="adm_backup_restore"),
             InlineKeyboardButton(text="\U0001f4cb \u062a\u0627\u0631\u06cc\u062e\u0686\u0647",               callback_data="adm_backup_history")],
            [InlineKeyboardButton(text=toggle,                                                                callback_data="adm_backup_toggle")],
            [InlineKeyboardButton(text="\U0001f50d \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u062e\u0648\u062f\u06a9\u0627\u0631 \u06af\u0631\u0648\u0647", callback_data="adm_backup_detect_group")],
            [InlineKeyboardButton(text="\u23f1 \u0641\u0627\u0635\u0644\u0647 \u0632\u0645\u0627\u0646\u06cc",  callback_data="adm_backup_set_interval"),
             InlineKeyboardButton(text="\u270f\ufe0f \u0622\u06cc\u062f\u06cc \u062f\u0633\u062a\u06cc",       callback_data="adm_backup_set_group")],
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a",                     callback_data="adm_settings")],
        ]),
        parse_mode="HTML"
    )


# ── شناسایی خودکار ────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_detect_group")
async def adm_backup_detect_group(cb: CallbackQuery, state: FSMContext):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(BackupState.waiting_forward_msg)
    await cb.message.edit_text(
        "\U0001f50d <b>\u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u062e\u0648\u062f\u06a9\u0627\u0631 \u06af\u0631\u0648\u0647</b>\n\n"
        "<b>\u0631\u0648\u0634 \u06f1 \u2014 Forward \u067e\u06cc\u0627\u0645 \u0627\u0632 \u06af\u0631\u0648\u0647:</b>\n"
        "\u2022 \u0628\u0647 \u06af\u0631\u0648\u0647 \u0628\u0631\u0648 \u2192 \u06cc\u06a9 \u067e\u06cc\u0627\u0645 \u0631\u0627 forward \u06a9\u0646 \u0628\u0647 \u0627\u06cc\u0646\u062c\u0627\n\n"
        "<b>\u0631\u0648\u0634 \u06f2 \u2014 \u062f\u0633\u062a\u0648\u0631 \u062f\u0631 \u06af\u0631\u0648\u0647:</b>\n"
        "\u2022 \u062f\u0631 \u06af\u0631\u0648\u0647 \u062f\u0633\u062a\u0648\u0631 \u0632\u06cc\u0631 \u0631\u0627 \u0628\u0632\u0646:\n"
        "<code>/backup_id</code>\n\n"
        "\u0628\u0627\u062a \u0622\u06cc\u062f\u06cc \u06af\u0631\u0648\u0647 \u0631\u0627 \u0628\u0631\u0645\u06cc\u200c\u06af\u0631\u062f\u0627\u0646\u062f \u0648 \u0628\u0631\u0627\u06cc \u062a\u0623\u06cc\u06cc\u062f \u0628\u0647 \u0634\u0645\u0627 \u0645\u06cc\u200c\u0641\u0631\u0633\u062f.\n\n"
        "/cancel \u0628\u0631\u0627\u06cc \u0644\u063a\u0648.",
        parse_mode="HTML"
    )


# ── دریافت forward از گروه ────────────────────────────────────────────────────
@router.message(BackupState.waiting_forward_msg)
async def adm_backup_forward_handler(msg: Message, state: FSMContext, bot: Bot):
    if not _sa(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear()
        await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f.")
        return
    group_id = None
    group_title = None
    if msg.forward_from_chat:
        chat = msg.forward_from_chat
        if chat.type in ("group", "supergroup"):
            group_id = chat.id
            group_title = chat.title or str(chat.id)
    if group_id is None and msg.text:
        try:
            group_id = int(msg.text.strip())
            group_title = str(group_id)
        except ValueError:
            pass
    if group_id is None:
        await msg.answer(
            "\u274c \u0646\u062a\u0648\u0646\u0633\u062a\u0645 \u0622\u06cc\u062f\u06cc \u06af\u0631\u0648\u0647 \u0631\u0627 \u062a\u0634\u062e\u06cc\u0635 \u062f\u0647\u0645.\n\n"
            "\u0644\u0637\u0641\u0627\u064b \u06cc\u06a9 \u067e\u06cc\u0627\u0645 \u0627\u0632 \u06af\u0631\u0648\u0647 forward \u06a9\u0646\u06cc\u062f \u06cc\u0627 \u062f\u0631 \u06af\u0631\u0648\u0647 /backup_id \u0628\u0632\u0646\u06cc\u062f."
        )
        return
    try:
        await bot.send_message(
            group_id,
            f"\U0001f916 <b>\u062a\u0633\u062a \u0627\u062a\u0635\u0627\u0644 \u0628\u06a9\u0627\u067e</b>\n\n"
            f"\u2705 \u06af\u0631\u0648\u0647 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0634\u062f!\n"
            f"\U0001f4cc \u0622\u06cc\u062f\u06cc: <code>{group_id}</code>\n"
            f"\U0001f4e6 \u0628\u06a9\u0627\u067e\u200c\u0647\u0627 \u0627\u06cc\u0646\u062c\u0627 \u0627\u0631\u0633\u0627\u0644 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f.",
            parse_mode="HTML"
        )
        await state.clear()
        async with AsyncSessionLocal() as session:
            await ss(session, "backup_group_id", str(group_id))
            await session.commit()
        await msg.answer(
            f"\u2705 <b>\u06af\u0631\u0648\u0647 \u0628\u0627 \u0645\u0648\u0641\u0642\u06cc\u062a \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f!</b>\n\n"
            f"\U0001f4cc \u0646\u0627\u0645: <b>{group_title}</b>\n"
            f"\U0001f194 \u0622\u06cc\u062f\u06cc: <code>{group_id}</code>\n\n"
            f"\u067e\u06cc\u0627\u0645 \u062a\u0633\u062a \u0628\u0647 \u06af\u0631\u0648\u0647 \u0627\u0631\u0633\u0627\u0644 \u0634\u062f.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f4e4 \u0628\u06a9\u0627\u067e \u0641\u0648\u0631\u06cc \u0628\u0632\u0646", callback_data="adm_backup_now")],
                [InlineKeyboardButton(text="\U0001f5c4 \u067e\u0646\u0644 \u0628\u06a9\u0627\u067e",                         callback_data="adm_backup")],
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.answer(
            f"\u274c \u062e\u0637\u0627 \u062f\u0631 \u0627\u0631\u0633\u0627\u0644 \u0628\u0647 \u06af\u0631\u0648\u0647:\n<code>{e}</code>\n\n"
            "\u2022 \u0645\u0637\u0645\u0626\u0646 \u0634\u0648\u06cc\u062f \u0628\u0627\u062a \u0639\u0636\u0648 \u06af\u0631\u0648\u0647 \u0627\u0633\u062a\n"
            "\u2022 \u0628\u0627\u062a \u0628\u0627\u06cc\u062f \u0627\u062f\u0645\u06cc\u0646 \u06af\u0631\u0648\u0647 \u0628\u0627\u0634\u062f",
            parse_mode="HTML"
        )


# ── /backup_id در گروه ────────────────────────────────────────────────────────
@router.message(F.text == "/backup_id")
async def cmd_backup_id_in_group(msg: Message, bot: Bot):
    if msg.chat.type not in ("group", "supergroup"):
        return
    chat_id    = msg.chat.id
    chat_title = msg.chat.title or str(chat_id)
    await msg.answer(
        f"\U0001f916 \u0622\u06cc\u062f\u06cc \u0627\u06cc\u0646 \u06af\u0631\u0648\u0647: <code>{chat_id}</code>\n"
        f"\u062f\u0631 \u062d\u0627\u0644 \u0627\u0631\u0633\u0627\u0644 \u0628\u0647 \u0627\u062f\u0645\u06cc\u0646...",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(
            SUPERADMIN_ID,
            f"\U0001f50d <b>\u06af\u0631\u0648\u0647 \u0634\u0646\u0627\u0633\u0627\u06cc\u06cc \u0634\u062f!</b>\n\n"
            f"\U0001f4cc \u0646\u0627\u0645: <b>{chat_title}</b>\n"
            f"\U0001f194 \u0622\u06cc\u062f\u06cc: <code>{chat_id}</code>\n\n"
            f"\u0622\u06cc\u0627 \u0627\u06cc\u0646 \u06af\u0631\u0648\u0647 \u0631\u0627 \u0628\u0647 \u0639\u0646\u0648\u0627\u0646 \u06af\u0631\u0648\u0647 \u0628\u06a9\u0627\u067e \u062a\u0646\u0638\u06cc\u0645 \u06a9\u0646\u06cc\u0645?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"\u2705 \u0628\u0644\u0647\u060c {chat_title[:30]} \u0631\u0627 \u062a\u0646\u0638\u06cc\u0645 \u06a9\u0646",
                    callback_data=f"adm_bkg_{chat_id}"
                )],
                [InlineKeyboardButton(text="\u274c \u062e\u06cc\u0631", callback_data="adm_backup")],
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Could not notify admin: {e}")


# ── تأیید ست کردن گروه از دکمه ───────────────────────────────────────────────
@router.callback_query(F.data.startswith("adm_bkg_"))
async def adm_backup_confirm_group(cb: CallbackQuery, bot: Bot):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    chat_id = int(cb.data.split("adm_bkg_")[1])
    async with AsyncSessionLocal() as session:
        await ss(session, "backup_group_id", str(chat_id))
        await session.commit()
    await cb.answer("\u2705 \u06af\u0631\u0648\u0647 \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f!", show_alert=True)
    try:
        await bot.send_message(
            chat_id,
            "\u2705 <b>\u0627\u06cc\u0646 \u06af\u0631\u0648\u0647 \u0628\u0647 \u0639\u0646\u0648\u0627\u0646 \u06af\u0631\u0648\u0647 \u0628\u06a9\u0627\u067e \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f.\n\u0628\u06a9\u0627\u067e\u200c\u0647\u0627 \u0627\u06cc\u0646\u062c\u0627 \u0627\u0631\u0633\u0627\u0644 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f.</b>",
            parse_mode="HTML"
        )
    except Exception: pass
    await cb.message.edit_text(
        f"\u2705 <b>\u06af\u0631\u0648\u0647 \u0628\u06a9\u0627\u067e \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f!</b>\n\n"
        f"\U0001f194 \u0622\u06cc\u062f\u06cc: <code>{chat_id}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f4e4 \u0628\u06a9\u0627\u067e \u0641\u0648\u0631\u06cc \u0628\u0632\u0646", callback_data="adm_backup_now")],
            [InlineKeyboardButton(text="\U0001f5c4 \u067e\u0646\u0644 \u0628\u06a9\u0627\u067e",                          callback_data="adm_backup")],
        ]),
        parse_mode="HTML"
    )


# ── بکاپ فوری ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_now")
async def adm_backup_now(cb: CallbackQuery, bot: Bot):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer("\u23f3 \u062f\u0631 \u062d\u0627\u0644 \u0633\u0627\u062e\u062a \u0628\u06a9\u0627\u067e...", show_alert=False)
    msg = await cb.message.edit_text(
        "\u23f3 <b>\u062f\u0631 \u062d\u0627\u0644 \u0633\u0627\u062e\u062a \u0628\u06a9\u0627\u067e...</b>\n\n"
        "\U0001f504 dump \u062f\u06cc\u062a\u0627\u0628\u06cc\u0633...\n\U0001f4c1 \u0641\u0634\u0631\u062f\u0647\u200c\u0633\u0627\u0632\u06cc...",
        parse_mode="HTML"
    )
    try:
        zip_bytes, filename, stats = await create_backup("manual")
        sent = await send_backup_to_group(bot, zip_bytes, filename, stats)
        lines = ["\u2705 <b>\u0628\u06a9\u0627\u067e \u0633\u0627\u062e\u062a\u0647 \u0634\u062f!</b>\n",
                 f"\U0001f4e6 \u062d\u062c\u0645: <code>{stats.get('total_size','?')}</code>",
                 f"\U0001f4c4 \u0641\u0627\u06cc\u0644: <code>{filename}</code>\n"]
        for k, v in stats.get("files", {}).items():
            lines.append(f"  \u2022 {k}: <code>{v}</code>")
        lines.append("\n\u2705 \u0628\u0647 \u06af\u0631\u0648\u0647 \u0627\u0631\u0633\u0627\u0644 \u0634\u062f." if sent
                     else "\n\u26a0\ufe0f \u06af\u0631\u0648\u0647 \u062a\u0646\u0638\u06cc\u0645 \u0646\u0634\u062f\u0647 \u2014 \u0641\u0627\u06cc\u0644 \u0645\u0633\u062a\u0642\u06cc\u0645 \u0627\u0631\u0633\u0627\u0644 \u0634\u062f:")
        await msg.edit_text("\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_backup")]
            ]), parse_mode="HTML")
        if not sent:
            from aiogram.types import BufferedInputFile
            await bot.send_document(cb.from_user.id,
                BufferedInputFile(zip_bytes, filename=filename),
                caption=f"\U0001f5c4 \u0628\u06a9\u0627\u067e \u062f\u0633\u062a\u06cc\n\U0001f4e6 {stats.get('total_size','?')}")
    except Exception as e:
        logger.error(f"Manual backup error: {e}")
        await msg.edit_text(f"\u274c <b>\u062e\u0637\u0627:</b>\n<code>{str(e)[:300]}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f519", callback_data="adm_backup")]
            ]), parse_mode="HTML")


# ── toggle ────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_toggle")
async def adm_backup_toggle(cb: CallbackQuery, bot: Bot):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    async with AsyncSessionLocal() as session:
        cur = await gs(session, "backup_auto_enabled", "1")
        new = "0" if cur == "1" else "1"
        await ss(session, "backup_auto_enabled", new)
        await session.commit()
    if new == "1":
        from services.backup_service import start_scheduler
        start_scheduler(bot)
        await cb.answer("\U0001f7e2 \u0628\u06a9\u0627\u067e \u062e\u0648\u062f\u06a9\u0627\u0631 \u0641\u0639\u0627\u0644 \u0634\u062f", show_alert=True)
    else:
        from services.backup_service import stop_scheduler
        stop_scheduler()
        await cb.answer("\U0001f534 \u0628\u06a9\u0627\u067e \u062e\u0648\u062f\u06a9\u0627\u0631 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0634\u062f", show_alert=True)
    await adm_backup(cb)


# ── تنظیم دستی گروه ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_set_group")
async def adm_backup_set_group(cb: CallbackQuery, state: FSMContext):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(BackupState.waiting_group_id)
    await cb.message.edit_text(
        "\u270f\ufe0f <b>\u0648\u0627\u0631\u062f \u06a9\u0631\u062f\u0646 \u062f\u0633\u062a\u06cc \u0622\u06cc\u062f\u06cc</b>\n\n"
        "\u0622\u06cc\u062f\u06cc \u0639\u062f\u062f\u06cc \u06af\u0631\u0648\u0647 \u0631\u0627 \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f:\n"
        "<i>\u0645\u062b\u0627\u0644: -1001234567890</i>\n\n/cancel \u0628\u0631\u0627\u06cc \u0644\u063a\u0648.", parse_mode="HTML")


@router.message(BackupState.waiting_group_id)
async def adm_backup_group_input(msg: Message, state: FSMContext, bot: Bot):
    if not _sa(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    try:
        gid_int = int((msg.text or "").strip())
    except ValueError:
        await msg.answer("\u274c \u0622\u06cc\u062f\u06cc \u0628\u0627\u06cc\u062f \u0639\u062f\u062f\u06cc \u0628\u0627\u0634\u062f."); return
    try:
        await bot.send_message(gid_int,
            "\u2705 <b>\u06af\u0631\u0648\u0647 \u0628\u06a9\u0627\u067e \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f!</b>", parse_mode="HTML")
        await state.clear()
        async with AsyncSessionLocal() as session:
            await ss(session, "backup_group_id", str(gid_int))
            await session.commit()
        await msg.answer(f"\u2705 \u06af\u0631\u0648\u0647 <code>{gid_int}</code> \u062a\u0646\u0638\u06cc\u0645 \u0634\u062f.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f5c4 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_backup")]
            ]), parse_mode="HTML")
    except Exception as e:
        await msg.answer(f"\u274c \u062e\u0637\u0627:\n<code>{e}</code>", parse_mode="HTML")


# ── فاصله زمانی ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_set_interval")
async def adm_backup_set_interval(cb: CallbackQuery, state: FSMContext):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(BackupState.waiting_interval)
    await cb.message.edit_text(
        "\u23f1 <b>\u0641\u0627\u0635\u0644\u0647 \u0632\u0645\u0627\u0646\u06cc \u0628\u06a9\u0627\u067e \u062e\u0648\u062f\u06a9\u0627\u0631</b>\n\n\u06cc\u06a9\u06cc \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u26a1 \u0647\u0631 \u06f1 \u0633\u0627\u0639\u062a",   callback_data="adm_bki_1"),
             InlineKeyboardButton(text="\U0001f550 \u0647\u0631 \u06f3 \u0633\u0627\u0639\u062a",  callback_data="adm_bki_3")],
            [InlineKeyboardButton(text="\U0001f555 \u0647\u0631 \u06f6 \u0633\u0627\u0639\u062a",  callback_data="adm_bki_6"),
             InlineKeyboardButton(text="\U0001f55b \u0647\u0631 \u06f1\u06f2 \u0633\u0627\u0639\u062a", callback_data="adm_bki_12")],
            [InlineKeyboardButton(text="\U0001f4c5 \u0647\u0631 \u06f2\u06f4 \u0633\u0627\u0639\u062a", callback_data="adm_bki_24")],
            [InlineKeyboardButton(text="\U0001f519 \u0644\u063a\u0648", callback_data="adm_backup")],
        ]), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_bki_"))
async def adm_bki_quick(cb: CallbackQuery, state: FSMContext):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    hours = cb.data.split("_")[-1]
    await state.clear()
    async with AsyncSessionLocal() as session:
        await ss(session, "backup_interval_hours", hours)
        await session.commit()
    await cb.answer(f"\u2705 \u0647\u0631 {hours} \u0633\u0627\u0639\u062a", show_alert=True)
    await adm_backup(cb)


@router.message(BackupState.waiting_interval)
async def adm_backup_interval_input(msg: Message, state: FSMContext):
    if not _sa(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    try:
        h = max(1, int((msg.text or "").strip()))
    except ValueError:
        await msg.answer("\u274c \u0639\u062f\u062f \u0635\u062d\u06cc\u062d \u0648\u0627\u0631\u062f \u06a9\u0646\u06cc\u062f."); return
    await state.clear()
    async with AsyncSessionLocal() as session:
        await ss(session, "backup_interval_hours", str(h))
        await session.commit()
    await msg.answer(f"\u2705 \u0641\u0627\u0635\u0644\u0647 \u0628\u06a9\u0627\u067e: <b>\u0647\u0631 {h} \u0633\u0627\u0639\u062a</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f5c4 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_backup")]
        ]), parse_mode="HTML")


# ── بازگردانی ─────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_restore")
async def adm_backup_restore(cb: CallbackQuery, state: FSMContext):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    await state.set_state(BackupState.waiting_restore_file)
    await cb.message.edit_text(
        "\u267b\ufe0f <b>\u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0627\u0632 \u0628\u06a9\u0627\u067e</b>\n\n"
        "\u26a0\ufe0f <b>\u0647\u0634\u062f\u0627\u0631:</b> \u062a\u0645\u0627\u0645 \u062f\u0627\u062f\u0647\u200c\u0647\u0627\u06cc \u0641\u0639\u0644\u06cc \u062c\u0627\u06cc\u06af\u0632\u06cc\u0646 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f!\n\n"
        "\u0641\u0627\u06cc\u0644 <code>.zip</code> \u0628\u06a9\u0627\u067e \u0631\u0627 \u0627\u0631\u0633\u0627\u0644 \u06a9\u0646\u06cc\u062f.\n\n/cancel \u0628\u0631\u0627\u06cc \u0644\u063a\u0648.", parse_mode="HTML")


@router.message(BackupState.waiting_restore_file)
async def adm_backup_restore_file(msg: Message, state: FSMContext, bot: Bot):
    if not _sa(msg.from_user.id): return
    if msg.text and msg.text.strip() == "/cancel":
        await state.clear(); await msg.answer("\u274c \u0644\u063a\u0648 \u0634\u062f."); return
    if not msg.document:
        await msg.answer("\u274c \u0644\u0637\u0641\u0627\u064b \u0641\u0627\u06cc\u0644 zip \u0627\u0631\u0633\u0627\u0644 \u06a9\u0646\u06cc\u062f."); return
    if not msg.document.file_name.endswith(".zip"):
        await msg.answer("\u274c \u0641\u0642\u0637 \u0641\u0627\u06cc\u0644 .zip \u0642\u0628\u0648\u0644 \u0645\u06cc\u200c\u0634\u0648\u062f."); return
    await state.clear()
    status_msg = await msg.answer("\u23f3 <b>\u062f\u0631 \u062d\u0627\u0644 \u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc...</b>", parse_mode="HTML")
    try:
        file = await bot.get_file(msg.document.file_id)
        buf  = await bot.download_file(file.file_path)
        zip_bytes = buf.read()
        result = await restore_from_zip(zip_bytes)
        lines = ["\u267b\ufe0f <b>\u0646\u062a\u06cc\u062c\u0647 \u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc:</b>\n"]
        for k, v in result.items():
            if k == "metadata":
                if isinstance(v, dict):
                    lines.append(f"\U0001f4cb \u0628\u06a9\u0627\u067e \u0627\u0632: <code>{v.get('timestamp','?')}</code>")
                continue
            lines.append(f"  \u2022 {k}: {v}")
        lines.append("\n\u26a0\ufe0f \u0628\u0631\u0627\u06cc \u0627\u0639\u0645\u0627\u0644 \u06a9\u0627\u0645\u0644\u060c \u0628\u0627\u062a \u0631\u0627 \u0631\u06cc\u0633\u062a\u0627\u0631\u062a \u06a9\u0646\u06cc\u062f.")
        await status_msg.edit_text("\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f5c4 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_backup")]
            ]), parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"\u274c <b>\u062e\u0637\u0627:</b>\n<code>{str(e)[:300]}</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f519", callback_data="adm_backup")]
            ]), parse_mode="HTML")


# ── تاریخچه ──────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "adm_backup_history")
async def adm_backup_history(cb: CallbackQuery):
    if not _sa(cb.from_user.id):
        await cb.answer("\u26d4\ufe0f", show_alert=True); return
    await cb.answer()
    async with AsyncSessionLocal() as session:
        last_at  = await gs(session, "backup_last_at",        "\u0647\u0631\u06af\u0632")
        group_id = await gs(session, "backup_group_id",       "\u062a\u0646\u0638\u06cc\u0645 \u0646\u0634\u062f\u0647")
        interval = await gs(session, "backup_interval_hours", "1")
        auto_on  = await gs(session, "backup_auto_enabled",   "1")
    status = "\U0001f7e2 \u0641\u0639\u0627\u0644" if auto_on == "1" else "\U0001f534 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644"
    await cb.message.edit_text(
        f"\U0001f4cb <b>\u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0628\u06a9\u0627\u067e</b>\n\n"
        f"\U0001f550 \u0622\u062e\u0631\u06cc\u0646 \u0628\u06a9\u0627\u067e: <b>{last_at}</b>\n"
        f"\U0001f4cc \u06af\u0631\u0648\u0647: <code>{group_id}</code>\n"
        f"\u23f1 \u0641\u0627\u0635\u0644\u0647: <b>\u0647\u0631 {interval} \u0633\u0627\u0639\u062a</b>\n"
        f"\U0001f504 \u0648\u0636\u0639\u06cc\u062a: <b>{status}</b>\n\n"
        f"<i>\u0628\u06a9\u0627\u067e\u200c\u0647\u0627\u06cc \u0642\u0628\u0644\u06cc \u062f\u0631 \u06af\u0631\u0648\u0647 \u0645\u0648\u062c\u0648\u062f\u0646\u062f.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f519 \u0628\u0627\u0632\u06af\u0634\u062a", callback_data="adm_backup")]
        ]), parse_mode="HTML")
