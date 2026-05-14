#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[FIX]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

DIR="/opt/telegram-session-bot"
cd "$DIR"

log "=== TSB Auto-Fix Script ==="

# 1. Pull latest code
log "Pulling latest code..."
git fetch origin
git reset --hard origin/main

# 2. Check .env
log "Checking .env..."
if [ ! -f .env ]; then
    err ".env not found!"
    exit 1
fi

ADMIN_ID=$(grep '^ADMIN_ID=' .env | cut -d'=' -f2 | tr -d '\r\n ')
BOT_TOKEN=$(grep '^BOT_TOKEN=' .env | cut -d'=' -f2 | tr -d '\r\n ')
API_ID=$(grep '^API_ID=' .env | cut -d'=' -f2 | tr -d '\r\n ')
API_HASH=$(grep '^API_HASH=' .env | cut -d'=' -f2 | tr -d '\r\n ')

log "ADMIN_ID  = $ADMIN_ID"
log "BOT_TOKEN = ${BOT_TOKEN:0:10}..."
log "API_ID    = $API_ID"

if [ -z "$ADMIN_ID" ] || [ "$ADMIN_ID" = "0" ]; then
    err "ADMIN_ID is empty or 0 in .env!"
    exit 1
fi

# 3. Patch start.py - remove middleware, hardcode ADMIN_ID check
log "Patching bot/handlers/start.py..."
cat > bot/handlers/start.py << PYEOF
import os
from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from services.session_manager import get_active_sessions, get_all_sessions
from services.task_manager import get_all_tasks

router = Router()

ADMIN_ID = ${ADMIN_ID}


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\U0001f4f1 \u0633\u0634\u0646\u200c\u0647\u0627", callback_data="menu_sessions"),
            InlineKeyboardButton(text="\u2699\ufe0f \u062a\u0633\u06a9\u200c\u0647\u0627", callback_data="menu_tasks"),
        ],
        [
            InlineKeyboardButton(text="\U0001f4ca \u0622\u0645\u0627\u0631", callback_data="menu_stats"),
            InlineKeyboardButton(text="\U0001f4be \u0628\u06a9\u0627\u067e", callback_data="menu_backup"),
        ],
        [
            InlineKeyboardButton(text="\U0001f310 \u067e\u0631\u0648\u06a9\u0633\u06cc", callback_data="menu_proxy"),
            InlineKeyboardButton(text="\U0001f4de \u0634\u0645\u0627\u0631\u0647 \u0645\u062c\u0627\u0632\u06cc", callback_data="menu_virtual"),
        ],
    ])


async def build_status(bot) -> str:
    sessions = await get_all_sessions()
    active   = [s for s in sessions if s.get("active")]
    tasks    = await get_all_tasks()
    running  = sum(1 for t in tasks if t["status"] == "running")
    pending  = sum(1 for t in tasks if t["status"] == "pending")
    done     = sum(1 for t in tasks if t["status"] == "completed")
    me = await bot.get_me()
    return (
        f"\U0001f916 <b>{me.first_name}</b> | @{me.username}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"\U0001f4f1 \u0633\u0634\u0646 \u0641\u0639\u0627\u0644: <b>{len(active)}</b> / {len(sessions)}\n"
        f"\u25b6\ufe0f \u062f\u0631 \u062d\u0627\u0644: <b>{running}</b>\n"
        f"\u23f3 \u062f\u0631 \u0635\u0641: <b>{pending}</b>\n"
        f"\u2705 \u062a\u0645\u0627\u0645 \u0634\u062f\u0647: <b>{done}</b>"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot):
    if message.from_user.id != ADMIN_ID:
        await message.answer(f"\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f\nID \u0634\u0645\u0627: <code>{message.from_user.id}</code>\n\u0627\u062f\u0645\u06cc\u0646: <code>${ADMIN_ID}</code>", parse_mode="HTML")
        return
    await state.clear()
    text = await build_status(bot)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, bot):
    if message.from_user.id != ADMIN_ID:
        await message.answer(f"\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f", parse_mode="HTML")
        return
    await state.clear()
    text = await build_status(bot)
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(lambda c: c.data in ("menu_main", "menu_refresh"))
async def cb_main(cb: CallbackQuery, state: FSMContext, bot):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("\u26d4\ufe0f \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f", show_alert=True)
        return
    await state.clear()
    text = await build_status(bot)
    await cb.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
PYEOF

# 4. Patch middlewares/admin.py - make it pass-through (no blocking)
log "Patching bot/middlewares/admin.py to pass-through..."
cat > bot/middlewares/admin.py << 'PYEOF'
from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Any


class AdminMiddleware(BaseMiddleware):
    """Pass-through middleware - admin check is done inline in each handler."""
    async def __call__(
        self,
        handler: Callable[[Any, dict], Awaitable[Any]],
        event: Any,
        data: dict
    ) -> Any:
        return await handler(event, data)
PYEOF

# 5. Rebuild and restart
log "Rebuilding Docker image..."
docker compose down
docker compose build --no-cache bot
docker compose up -d

# 6. Wait and check
log "Waiting 5s for bot to start..."
sleep 5

log "=== Bot logs ==="
docker logs tsb_bot --tail=30

# 7. Verify ADMIN_ID inside container
log "=== Verifying ADMIN_ID inside container ==="
docker exec tsb_bot python3 -c "import os; aid=os.getenv('ADMIN_ID','NOT_SET'); print(f'ADMIN_ID in container: {aid}')"

log "=== Done! ==="
echo ""
echo -e "${GREEN}Now send /start to your bot${NC}"
