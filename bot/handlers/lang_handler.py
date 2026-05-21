"""Language selection handler."""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from db.database import AsyncSessionLocal
from db.models import User
from services.user_service import set_language
from services.settings_service import get_setting
from i18n import t, lang_keyboard, LANGUAGES

router = Router()


async def _active_langs() -> list:
    async with AsyncSessionLocal() as s:
        raw = await get_setting(s, "active_languages", "en,fa,ar,he,ru")
    return [x.strip() for x in raw.split(",") if x.strip() in LANGUAGES]


@router.callback_query(F.data == "lang_select_screen")
async def lang_select_screen(cb: CallbackQuery):
    await cb.answer()
    active = await _active_langs()
    kb     = lang_keyboard(active)
    body   = "\n".join(label for code, label in LANGUAGES.items() if code in active)
    await cb.message.edit_text(
        f"🌍 <b>Choose your language / انتخاب زبان</b>\n\n{body}",
        reply_markup=kb, parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("set_lang_"))
async def set_lang_cb(cb: CallbackQuery, db_user: User = None):
    lang   = cb.data[len("set_lang_"):]
    active = await _active_langs()
    if lang not in active:
        await cb.answer("❌", show_alert=True)
        return
    async with AsyncSessionLocal() as s:
        await set_language(s, cb.from_user.id, lang)
        await s.commit()
    if db_user:
        db_user.language = lang
    await cb.answer(t("lang_saved", lang), show_alert=True)
    from handlers.user_handler import send_home
    await send_home(cb.message, db_user, lang=lang, edit=True)


@router.callback_query(F.data == "user_change_lang")
async def user_change_lang(cb: CallbackQuery, db_user: User = None):
    await cb.answer()
    active  = await _active_langs()
    lang    = getattr(db_user, "language", "en") or "en"
    kb      = lang_keyboard(active)
    kb.inline_keyboard.append(
        [InlineKeyboardButton(text=t("btn_back", lang), callback_data="user_home")]
    )
    current = LANGUAGES.get(lang, lang)
    body    = "\n".join(
        ("✅ " if code == lang else "   ") + label
        for code, label in LANGUAGES.items() if code in active
    )
    await cb.message.edit_text(
        f"🌐 <b>{t('btn_change_lang', lang)}</b>\n"
        f"Current / فعلی: <b>{current}</b>\n\n{body}",
        reply_markup=kb, parse_mode="HTML",
    )
