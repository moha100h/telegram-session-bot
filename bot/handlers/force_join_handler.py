"""Force-join verify handler — i18n aware."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.models import User
from services.force_join_service import get_force_join_settings, check_membership
from i18n import t

router = Router()


@router.callback_query(F.data == "fj_verify")
async def fj_verify(cb: CallbackQuery, db_user: User = None, user_lang: str = "en"):
    lang    = getattr(db_user, "language", None) or user_lang or "en"
    fj      = await get_force_join_settings()
    channel = fj["channel"].strip()
    if not channel:
        await cb.answer(t("fj_joined", lang), show_alert=False)
        try: await cb.message.delete()
        except Exception: pass
        return
    is_member = await check_membership(cb.bot, cb.from_user.id, channel)
    if is_member:
        await cb.answer(t("fj_joined", lang), show_alert=True)
        try: await cb.message.delete()
        except Exception: pass
        await cb.message.answer(
            f"<b>{t('fj_joined', lang)}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("btn_home", lang), callback_data="user_home")]
            ]),
            parse_mode="HTML",
        )
    else:
        ch_link = f"https://t.me/{channel.lstrip('@')}" if channel.startswith("@") else channel
        await cb.answer(t("fj_not_joined", lang), show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=t("btn_join_channel", lang), url=ch_link)],
                [InlineKeyboardButton(text=t("btn_verify_join",  lang), callback_data="fj_verify")],
            ]))
        except Exception: pass
