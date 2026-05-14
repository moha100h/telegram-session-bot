from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware

router = Router()
router.callback_query.middleware(AdminMiddleware())


@router.callback_query(F.data == "menu_virtual")
async def virtual_menu(cb: CallbackQuery):
    await cb.message.edit_text(
        "📞 <b>شماره مجازی</b>\n\n"
        "این بخش به زودی اضافه خواهد شد.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )
