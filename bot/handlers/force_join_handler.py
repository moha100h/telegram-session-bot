"""Force-join verify handler."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.models import User
from services.force_join_service import get_force_join_settings, check_membership

router = Router()


@router.callback_query(F.data == "fj_verify")
async def fj_verify(cb: CallbackQuery, db_user: User = None):
    fj = await get_force_join_settings()
    channel = fj["channel"].strip()

    if not channel:
        await cb.answer("\u2705 \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f!", show_alert=False)
        try:
            await cb.message.delete()
        except Exception:
            pass
        return

    is_member = await check_membership(cb.bot, cb.from_user.id, channel)

    if is_member:
        await cb.answer(
            "\u2705 \u0639\u0636\u0648\u06cc\u062a \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f! \u0627\u06a9\u0646\u0648\u0646 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc\u062f \u0627\u0632 \u0631\u0628\u0627\u062a \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.",
            show_alert=True
        )
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(
            "\u2705 <b>\u0639\u0636\u0648\u06cc\u062a \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f!</b>\n\n\u0627\u06a9\u0646\u0648\u0646 \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc\u062f \u0627\u0632 \u0631\u0628\u0627\u062a \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u06a9\u0646\u06cc\u062f.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="\U0001f3e0 \u0645\u0646\u0648\u06cc \u0627\u0635\u0644\u06cc",
                    callback_data="user_home"
                )]
            ]),
            parse_mode="HTML"
        )
    else:
        ch_link = (
            f"https://t.me/{channel.lstrip('@')}"
            if channel.startswith("@") else channel
        )
        await cb.answer(
            "\u274c \u0647\u0646\u0648\u0632 \u0639\u0636\u0648 \u06a9\u0627\u0646\u0627\u0644 \u0646\u0634\u062f\u0647\u200c\u0627\u06cc\u062f!",
            show_alert=True
        )
        try:
            await cb.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=fj["btn_join"],   url=ch_link)],
                    [InlineKeyboardButton(text=fj["btn_verify"], callback_data="fj_verify")],
                ])
            )
        except Exception:
            pass
