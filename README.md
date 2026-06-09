# 🤖 Telegram Session Bot — SMM Panel

ربات تلگرامی حرفه‌ای برای مدیریت سشن‌ها و پنل SMM با قابلیت Multi-Panel دستی.

## ✨ ویژگی‌ها

**پنل کاربری:** کیف پول USDT/TON/TRX | پنل SMMPass | پنل‌های دستی | پیگیری سفارشات

**پنل ادمین:** مدیریت کاربران | تایید واریز | Multi-Panel | بکاپ خودکار | تنظیمات کامل

## 🚀 نصب (یک دستور)

```bash
curl -fsSL https://raw.githubusercontent.com/moha100h/telegram-session-bot/main/install.sh | bash
```

یا:

```bash
git clone https://github.com/moha100h/telegram-session-bot.git /opt/telegram-session-bot
cd /opt/telegram-session-bot
sudo bash install.sh
```

فقط دو چیز لازم است:
- `BOT_TOKEN` — از @BotFather
- `ADMIN_ID` — آیدی عددی تلگرام شما

بقیه تنظیمات **خودکار** انجام می‌شود.

## 🖥️ سیستم‌عامل پشتیبانی‌شده

- Ubuntu 20.04 / 22.04 / 24.04
- Debian 11 / 12

## 🐳 دستورات Docker

```bash
docker compose logs -f bot     # لاگ زنده
docker compose restart bot     # ری‌استارت
docker compose ps              # وضعیت
sudo bash install.sh           # آپدیت
```

## ⚙️ تنظیمات

```bash
nano /opt/telegram-session-bot/.env
docker compose restart bot
```
