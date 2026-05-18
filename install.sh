#!/bin/bash
# Telegram Session Bot — Install/Update v3.0
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "\033[0;34m[INFO]\033[0m $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()    { echo -e "\n${CYAN}══════════════════════════════════════${NC}\n${CYAN}  $1${NC}\n${CYAN}══════════════════════════════════════${NC}"; }

INSTALL_DIR="/opt/telegram-session-bot"
REPO_URL="https://github.com/moha100h/telegram-session-bot.git"

step "1. پیش‌نیازها"
[[ $EUID -ne 0 ]] && error "با root اجرا کنید: sudo bash install.sh"
command -v curl &>/dev/null || apt-get install -y curl -qq
command -v git  &>/dev/null || apt-get install -y git  -qq
success "OK"

step "2. Docker"
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker && systemctl start docker
    success "Docker نصب شد"
else
    success "Docker: $(docker --version)"
fi
docker compose version &>/dev/null 2>&1 || \
    { apt-get install -y docker-compose-plugin -qq 2>/dev/null || \
      curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
           -o /usr/local/bin/docker-compose && chmod +x /usr/local/bin/docker-compose; }
success "Docker Compose OK"

step "3. سورس کد"
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR" && git fetch origin && git reset --hard origin/main && success "آپدیت شد"
else
    git clone "$REPO_URL" "$INSTALL_DIR" && success "Clone شد"
fi
cd "$INSTALL_DIR"

step "4. تنظیم .env"
if [ ! -f ".env" ]; then
    cp .env.example .env
    read -rp "  BOT_TOKEN: "                     BOT_TOKEN
    read -rp "  ADMIN_ID: "                      ADMIN_ID
    read -rp "  POSTGRES_PASSWORD (پسورد قوی): " PG_PASS
    sed -i "s/your_bot_token_here/$BOT_TOKEN/"       .env
    sed -i "s/your_telegram_id_here/$ADMIN_ID/"      .env
    sed -i "s/change_this_strong_password/$PG_PASS/" .env
    success ".env تنظیم شد"
else
    warn ".env موجود است — تغییر نمی‌دهیم"
fi

step "5. Build"
docker compose down --remove-orphans 2>/dev/null || true
docker compose build --no-cache bot
docker compose up -d
success "سرویس‌ها راه‌اندازی شدند"

step "6. Migrations"
for i in $(seq 1 30); do
    docker compose exec -T postgres pg_isready -U smm -d smmbot &>/dev/null && break
    sleep 2; [ $i -eq 30 ] && error "PostgreSQL راه‌اندازی نشد"
done
success "PostgreSQL آماده"
docker compose exec -T postgres psql -U smm -d smmbot < bot/db/migrations.sql \
    && success "Migrations OK" || warn "Migration با هشدار اجرا شد"

step "7. وضعیت"
sleep 5 && docker compose ps && echo "" && docker logs tsb_bot --tail=20

step "✅ نصب/آپدیت کامل شد!"
echo -e "\n${CYAN}  دستورات:${NC}"
echo "    docker compose logs -f bot   # لاگ"
echo "    docker compose restart bot   # ری‌استارت"
echo "    bash install.sh              # آپدیت"
echo -e "\n${YELLOW}  بکاپ‌ها: /app/data/backups/${NC}\n"
