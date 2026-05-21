# 🤖 Telegram Session Bot — SMM Panel

ربات تلگرامی حرفه‌ای برای مدیریت سشن‌ها و پنل SMM با قابلیت Multi-Panel دستی.

## ✨ ویژگی‌ها

**پنل کاربری:** کیف پول USDT/TON/TRX | پنل SMMPass | پنل‌های دستی | پیگیری سفارشات

**پنل ادمین:** مدیریت کاربران | تایید واریز | Multi-Panel | بکاپ خودکار | تنظیمات کامل

**بکاپ v3.0:**
- PostgreSQL dump (gzip + --clean)
- JSON export همه جداول (بدون نیاز به psql)
- Sessions + App data + Redis RDB
- SHA-256 checksum
- ذخیره local آخرین ۱۰ بکاپ در `/app/data/backups/`
- ارسال خودکار به گروه تلگرام
- بازگردانی کامل با verify

## 🚀 نصب

```bash
git clone https://github.com/moha100h/telegram-session-bot.git /opt/telegram-session-bot
cd /opt/telegram-session-bot
sudo bash install.sh
```

## ⚙️ پیکربندی

```bash
cp .env.example .env && nano .env
```

| متغیر | توضیح |
|---|---|
| `BOT_TOKEN` | توکن از @BotFather |
| `ADMIN_ID` | Telegram ID ادمین |
| `POSTGRES_PASSWORD` | پسورد قوی |

## 🐳 Docker

```bash
docker compose up -d
docker compose logs -f bot
git pull && docker compose build --no-cache bot && docker compose up -d
```

## 🗄 ساختار بکاپ

```
backup_auto_20260518_120000.zip
├── db/database_*.sql.gz    ← PostgreSQL dump
├── db/export_*.json.gz     ← JSON همه جداول
├── sessions/               ← سشن‌های تلگرام
├── data/                   ← داده‌های اپ
├── redis/dump.rdb          ← Redis snapshot
└── metadata.json           ← آمار + SHA-256
```

## 📁 ساختار پروژه

```
bot/
├── handlers/
│   ├── admin_handler.py
│   ├── user_handler.py
│   ├── panel_admin_handler.py
│   ├── panel_user_handler.py
│   ├── smmpass_handler.py
│   └── backup_handler.py
├── services/
│   ├── backup_service.py   ← v3.0
│   └── ...
└── db/
    ├── models.py
    ├── database.py
    └── migrations.sql      ← v3.0
```

## 📄 License MIT
