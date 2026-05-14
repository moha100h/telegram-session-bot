import asyncio
import logging
import os
from aiogram import Bot
from services.session_manager import get_session_names, verify_session

logger = logging.getLogger("session_checker")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHECK_INTERVAL = 6 * 3600


class SessionChecker:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def run(self):
        await asyncio.sleep(60)
        while True:
            try:
                await self._check_all()
            except Exception as e:
                logger.error("[SessionChecker] %s", e)
            await asyncio.sleep(CHECK_INTERVAL)

    async def _check_all(self):
        names = await get_session_names()
        if not names:
            return
        failed = []
        for name in names:
            r = await verify_session(name)
            if not r["ok"]:
                failed.append({"name": name, "error": r.get("error", "unknown")})
            await asyncio.sleep(1)
        if not failed:
            logger.info("[SessionChecker] All %d sessions OK", len(names))
            return
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        ok_count = len(names) - len(failed)
        lines = [
            "\u26a0\ufe0f <b>\u0628\u0631\u0631\u0633\u06cc \u062e\u0648\u062f\u06a9\u0627\u0631 \u0633\u0634\u0646\u200c\u0647\u0627</b>\n",
            "\u2705 \u0633\u0627\u0644\u0645: <b>" + str(ok_count) + "</b>",
            "\u274c \u0645\u0634\u06a9\u0644\u062f\u0627\u0631: <b>" + str(len(failed)) + "</b>\n",
        ]
        for f in failed:
            lines.append("\u2022 <code>" + f["name"] + "</code>: " + str(f["error"]))
        buttons = []
        for f in failed:
            buttons.append([
                InlineKeyboardButton(
                    text="\ud83d\udd04 \u062a\u0633\u062a \u0645\u062c\u062f\u062f " + f["name"],
                    callback_data="sc_retest_" + f["name"]
                ),
                InlineKeyboardButton(
                    text="\ud83d\uddd1 \u062d\u0630\u0641 " + f["name"],
                    callback_data="sc_delete_" + f["name"]
                ),
            ])
        try:
            await self.bot.send_message(
                ADMIN_ID,
                "\n".join(lines),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
        except Exception as e:
            logger.error("[SessionChecker] notify failed: %s", e)
