#!/bin/bash
# ============================================================
# Telegram Session Bot — Install / Update v3.2
# Ubuntu 20.04 / 22.04 / 24.04 / Debian 11 / 12
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1"; exit 1; }
step()    { echo -e "\n${CYAN}${BOLD}══════════════════════════════════════${NC}"; \
            echo -e "${CYAN}${BOLD}  $1${NC}"; \
            echo -e "${CYAN}${BOLD}══════════════════════════════════════${NC}"; }

INSTALL_DIR="/opt/telegram-session-bot"
REPO_URL="https://github.com/moha100h/telegram-session-bot.git"
VERSION="3.2"

echo -e "\n${CYAN}${BOLD}"
echo "  ████████╗███████╗██████╗      ██████╗  ██████╗ ████████╗"
echo "     ██╔══╝██╔════╝██╔══██╗     ██╔══██╗██╔═══██╗╚══██╔══╝"
echo "     ██║   ███████╗██████╔╝     ██████╔╝██║   ██║   ██║   "
echo "     ██║   ╚════██║██╔══██╗     ██╔══██╗██║   ██║   ██║   "
echo "     ██║   ███████║██████╔╝     ██████╔╝╚██████╔╝   ██║   "
echo "     ╚═╝   ╚══════╝╚═════╝      ╚═════╝  ╚═════╝    ╚═╝   "
echo -e "${NC}"
echo -e "  ${BOLD}Telegram Session Bot — SMM Panel v${VERSION}${NC}"
echo -e "  ${BLUE}https://github.com/moha100h/telegram-session-bot${NC}\n"

# ── بررسی root ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "با root اجرا کنید: sudo bash install.sh"

# ── پیش‌نیازها ────────────────────────────────────────────────────────────────
step "1/6 — پیش‌نیازها"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
for pkg in curl git ca-certificates gnupg openssl; do
    command -v $pkg &>/dev/null || apt-get install -y $pkg -qq
done
success "پیش‌نیازها OK"

# ── Docker (روی هر نسخه Ubuntu/Debian) ───────────────────────────────────────
step "2/6 — Docker"
if ! command -v docker &>/dev/null; then
    info "نصب Docker از get.docker.com ..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker --quiet
    systemctl start docker
    success "Docker نصب شد: $(docker --version)"
else
    success "Docker: $(docker --version)"
fi

# Docker Compose plugin یا standalone
if ! docker compose version &>/dev/null 2>&1; then
    info "نصب Docker Compose plugin..."
    apt-get install -y docker-compose-plugin -qq 2>/dev/null || true
    if ! docker compose version &>/dev/null 2>&1; then
        info "نصب Docker Compose standalone..."
        COMPOSE_VER=$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest \
            | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')
        curl -fsSL "https://github.com/docker/compose/releases/download/v${COMPOSE_VER}/docker-compose-linux-x86_64" \
            -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        ln -sf /usr/local/bin/docker-compose /usr/lib/docker/cli-plugins/docker-compose 2>/dev/null || true
    fi
fi
success "Docker Compose: $(docker compose version 2>/dev/null || docker-compose version)"

# ── سورس کد ──────────────────────────────────────────────────────────────────
step "3/6 — سورس کد"
if [ -d "$INSTALL_DIR/.git" ]; then
    info "آپدیت از GitHub..."
    cd "$INSTALL_DIR"
    git fetch origin --quiet
    git reset --hard origin/main --quiet
    success "آپدیت شد: $(git log --oneline -1)"
else
    info "Clone از GitHub..."
    git clone "$REPO_URL" "$INSTALL_DIR" --quiet
    success "Clone شد"
fi
cd "$INSTALL_DIR"

# ── تنظیم .env — فقط BOT_TOKEN و ADMIN_ID ───────────────────────────────────
step "4/6 — تنظیم .env"
if [ ! -f ".env" ]; then
    cp .env.example .env

    echo ""
    warn "فقط دو مورد زیر لازم است:"
    echo ""

    while true; do
        read -rp "  🤖 BOT_TOKEN (از @BotFather): " BOT_TOKEN
        [[ -n "$BOT_TOKEN" ]] && break
        warn "BOT_TOKEN نمی‌تواند خالی باشد"
    done

    while true; do
        read -rp "  👤 ADMIN_ID (آیدی عددی تلگرام): " ADMIN_ID
        [[ "$ADMIN_ID" =~ ^[0-9]+$ ]] && break
        warn "ADMIN_ID باید عدد باشد"
    done

    # پسورد postgres خودکار
    PG_PASS=$(openssl rand -hex 24)

    sed -i "s|your_bot_token_here|${BOT_TOKEN}|"       .env
    sed -i "s|your_telegram_id_here|${ADMIN_ID}|"      .env
    sed -i "s|change_this_strong_password|${PG_PASS}|" .env

    success ".env تنظیم شد (پسورد Postgres خودکار تولید شد)"
else
    warn ".env موجود است — تغییر نمی‌دهیم"
    info "برای ویرایش: nano $INSTALL_DIR/.env"
fi

# ── Build و راه‌اندازی ────────────────────────────────────────────────────────
step "5/6 — Build و راه‌اندازی"
docker compose down --remove-orphans 2>/dev/null || true
info "Build image (ممکن است چند دقیقه طول بکشد)..."
docker compose build --no-cache bot
docker compose up -d
success "سرویس‌ها راه‌اندازی شدند"

# ── Migrations ────────────────────────────────────────────────────────────────
step "6/6 — Database"
info "صبر برای PostgreSQL..."
RETRIES=0
until docker compose exec -T postgres pg_isready -U smm -d smmbot &>/dev/null; do
    RETRIES=$((RETRIES+1))
    [ $RETRIES -ge 30 ] && error "PostgreSQL در ۶۰ ثانیه راه‌اندازی نشد"
    sleep 2
done
success "PostgreSQL آماده"

info "اجرای migrations..."
docker compose exec -T postgres psql -U smm -d smmbot \
    < bot/db/migrations.sql 2>&1 | grep -v "^NOTICE" | grep -v "^$" || true
success "Migrations OK"

# ── وضعیت نهایی ──────────────────────────────────────────────────────────────
sleep 3
echo ""
docker compose ps
echo ""
info "آخرین لاگ‌ها:"
docker logs tsb_bot --tail=20 2>&1 || true
echo ""

echo -e "\n${GREEN}${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║   ✅  نصب با موفقیت انجام شد   ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${NC}\n"

echo -e "${CYAN}${BOLD}  دستورات مفید:${NC}"
echo -e "  ${BOLD}docker compose logs -f bot${NC}     # لاگ زنده"
echo -e "  ${BOLD}docker compose restart bot${NC}     # ری‌استارت"
echo -e "  ${BOLD}docker compose ps${NC}              # وضعیت"
echo -e "  ${BOLD}bash $0${NC}                        # آپدیت"
echo ""
echo -e "${YELLOW}  📁 مسیرها:${NC}"
echo -e "  تنظیمات: $INSTALL_DIR/.env"
echo -e "  سشن‌ها:   /app/sessions/"
echo -e "  بکاپ‌ها:  /app/data/backups/"
echo ""
