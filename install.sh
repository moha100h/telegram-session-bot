#!/bin/bash
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
INSTALL_DIR="/opt/telegram-session-bot"
REPO_URL="https://github.com/moha100h/telegram-session-bot.git"
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════╗"
echo "║     TelegramSessionBot Installer         ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"
[[ $EUID -ne 0 ]] && error "باید با root اجرا شود."
if ! command -v docker &>/dev/null; then
    info "نصب Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    success "Docker نصب شد."
else
    success "Docker از قبل نصب است."
fi
if [ -d "$INSTALL_DIR" ]; then
    warn "آپدیت ریپو..."
    cd "$INSTALL_DIR" && git pull
else
    info "کلون ریپو..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
if [ ! -f ".env" ]; then
    info "تنظیم .env ..."
    read -p "  BOT_TOKEN: "   BOT_TOKEN
    read -p "  ADMIN_ID: "    ADMIN_ID
    read -p "  SMM_API_URL: " SMM_API_URL
    read -p "  SMM_API_KEY: " SMM_API_KEY
    read -p "  USDT_WALLET: " USDT_WALLET
    read -p "  TON_WALLET: "  TON_WALLET
    read -p "  TRX_WALLET: "  TRX_WALLET
    DB_PASS=$(openssl rand -hex 16)
    cat > .env <<EOF
BOT_TOKEN=${BOT_TOKEN}
ADMIN_ID=${ADMIN_ID}
POSTGRES_DB=smmbot
POSTGRES_USER=smm
POSTGRES_PASSWORD=${DB_PASS}
REDIS_URL=redis://redis:6379/0
SMM_API_URL=${SMM_API_URL}
SMM_API_KEY=${SMM_API_KEY}
USDT_WALLET=${USDT_WALLET}
TON_WALLET=${TON_WALLET}
TRX_WALLET=${TRX_WALLET}
EOF
    success ".env ساخته شد."
else
    warn ".env از قبل وجود دارد."
fi
info "Build و راه‌اندازی..."
docker compose down --remove-orphans 2>/dev/null || true
docker compose build --no-cache
docker compose up -d
info "صبر 15 ثانیه..."
sleep 15
echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  نصب با موفقیت انجام شد!${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
docker compose ps
echo ""
docker logs tsb_bot --tail=10
echo ""
echo -e "  لاگ زنده: ${YELLOW}docker logs tsb_bot -f${NC}"
echo -e "  آپدیت:    ${YELLOW}cd $INSTALL_DIR && git pull && docker compose build --no-cache bot && docker compose up -d${NC}"
