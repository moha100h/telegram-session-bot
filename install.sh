#!/bin/bash
set -e

# ================================================================
# Telegram Session Bot - Auto Installer
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/moha100h/telegram-session-bot/main/install.sh)
# ================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="/opt/telegram-session-bot"
REPO="https://github.com/moha100h/telegram-session-bot.git"

print_banner() {
    echo -e "${CYAN}"
    echo '  _____ ____  ____    ____        _   '
    echo ' |_   _/ ___|| __ )  | __ )  ___ | |_ '
    echo "   | | \___ \|  _ \  |  _ \ / _ \| __|"
    echo '   | |  ___) | |_) | | |_) | (_) | |_ '
    echo '   |_| |____/|____/  |____/ \___/ \__|'
    echo -e "${NC}"
    echo -e "${BOLD}  Telegram Session Bot - Auto Installer${NC}"
    echo -e "  ${BLUE}https://github.com/moha100h/telegram-session-bot${NC}"
    echo ""
}

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
ask()  { echo -e "${YELLOW}[?]${NC} $1"; }

# ── Root check ──────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    err "لطفاً با دسترسی root اجرا کنید: sudo bash install.sh"
fi

print_banner

# ── OS check ────────────────────────────────────────────────────
if ! command -v apt-get &>/dev/null; then
    err "فقط Ubuntu/Debian پشتیبانی می‌شود"
fi

info "سیستم‌عامل: $(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2)"
info "آدرس IP: $(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
echo ""

# ── Collect config ──────────────────────────────────────────────
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  تنظیمات بات${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

ask "توکن بات (از @BotFather):"
read -r BOT_TOKEN
[ -z "$BOT_TOKEN" ] && err "توکن بات الزامی است"

ask "آیدی عددی ادمین (از @userinfobot):"
read -r ADMIN_IDS
[ -z "$ADMIN_IDS" ] && err "آیدی ادمین الزامی است"

ask "API_ID (از my.telegram.org/apps):"
read -r API_ID
[ -z "$API_ID" ] && err "API_ID الزامی است"

ask "API_HASH (از my.telegram.org/apps):"
read -r API_HASH
[ -z "$API_HASH" ] && err "API_HASH الزامی است"

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}تنظیمات دریافت شد. شروع نصب...${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Update system ───────────────────────────────────────────────
info "بروزرسانی سیستم..."
apt-get update -qq
apt-get install -y -qq curl git ca-certificates gnupg lsb-release
log "پکیج‌های پایه نصب شدند"

# ── Install Docker ───────────────────────────────────────────────
if command -v docker &>/dev/null; then
    log "Docker قبلاً نصب است: $(docker --version)"
else
    info "نصب Docker..."
    curl -fsSL https://get.docker.com | sh -s -- -q
    systemctl enable docker --now
    log "Docker نصب شد: $(docker --version)"
fi

# ── Install docker compose plugin ───────────────────────────────
if docker compose version &>/dev/null; then
    log "Docker Compose موجود است"
else
    info "نصب Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
    log "Docker Compose نصب شد"
fi

# ── Clone / update repo ──────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    info "بروزرسانی پروژه..."
    cd "$INSTALL_DIR"
    git pull -q
    log "پروژه بروزرسانی شد"
else
    info "دانلود پروژه..."
    rm -rf "$INSTALL_DIR"
    git clone -q "$REPO" "$INSTALL_DIR"
    log "پروژه دانلود شد"
fi

cd "$INSTALL_DIR"

# ── Create directories ───────────────────────────────────────────
mkdir -p sessions backups data
log "پوشه‌ها ساخته شدند"

# ── Write .env ───────────────────────────────────────────────────
cat > .env << EOF
# Telegram Bot
BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}

# Telegram API
API_ID=${API_ID}
API_HASH=${API_HASH}

# Redis
REDIS_URL=redis://redis:6379

# Paths
SESSIONS_DIR=/app/sessions
DATA_DIR=/app/data
BACKUPS_DIR=/app/backups
EOF
log "فایل .env ساخته شد"

# ── Build & start ────────────────────────────────────────────────
info "ساخت و اجرای containers (ممکن است چند دقیقه طول بکشد)..."
docker compose down --remove-orphans 2>/dev/null || true
docker compose up -d --build
log "Containers اجرا شدند"

# ── Wait and check ───────────────────────────────────────────────
info "صبر برای راه‌اندازی..."
sleep 8

BOT_STATUS=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        if 'bot' in d.get('Name','').lower():
            print(d.get('State','unknown'))
            break
    except: pass
" 2>/dev/null || docker compose ps | grep bot | awk '{print $4}')

# ── Create update script ─────────────────────────────────────────
cat > /usr/local/bin/tsb-update << 'UPDATESCRIPT'
#!/bin/bash
cd /opt/telegram-session-bot
git pull
docker compose up -d --build
echo "✅ بروزرسانی کامل شد"
UPDATESCRIPT
chmod +x /usr/local/bin/tsb-update

# ── Create logs script ───────────────────────────────────────────
cat > /usr/local/bin/tsb-logs << 'LOGSSCRIPT'
#!/bin/bash
cd /opt/telegram-session-bot
case "$1" in
    worker) docker compose logs -f worker ;;
    *) docker compose logs -f bot ;;
esac
LOGSSCRIPT
chmod +x /usr/local/bin/tsb-logs

# ── Create restart script ────────────────────────────────────────
cat > /usr/local/bin/tsb-restart << 'RESTARTSCRIPT'
#!/bin/bash
cd /opt/telegram-session-bot
docker compose restart
echo "✅ ری‌استارت شد"
RESTARTSCRIPT
chmod +x /usr/local/bin/tsb-restart

# ── Create status script ─────────────────────────────────────────
cat > /usr/local/bin/tsb-status << 'STATUSSCRIPT'
#!/bin/bash
cd /opt/telegram-session-bot
docker compose ps
STATUSSCRIPT
chmod +x /usr/local/bin/tsb-status

log "دستورات مدیریتی نصب شدند"

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  ✅ نصب با موفقیت انجام شد!${NC}"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}📁 مسیر نصب:${NC}  $INSTALL_DIR"
echo -e "  ${BOLD}🤖 بات:${NC}       در تلگرام /start بزنید"
echo ""
echo -e "  ${BOLD}دستورات مدیریتی:${NC}"
echo -e "  ${CYAN}tsb-status${NC}   — وضعیت containers"
echo -e "  ${CYAN}tsb-logs${NC}     — لاگ بات"
echo -e "  ${CYAN}tsb-logs worker${NC} — لاگ worker"
echo -e "  ${CYAN}tsb-restart${NC}  — ری‌استارت"
echo -e "  ${CYAN}tsb-update${NC}   — بروزرسانی از GitHub"
echo ""
echo -e "  ${BOLD}مسیر فایل‌ها:${NC}"
echo -e "  ${CYAN}$INSTALL_DIR/sessions/${NC}  — فایل‌های .session"
echo -e "  ${CYAN}$INSTALL_DIR/backups/${NC}   — بکاپ‌ها"
echo -e "  ${CYAN}$INSTALL_DIR/.env${NC}       — تنظیمات"
echo ""
