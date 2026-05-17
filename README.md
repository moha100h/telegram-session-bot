# 🤖 TelegramSessionBot

ربات تلگرامی حرفه‌ای برای مدیریت سفارشات SMM Panel با پنل ادمین کامل و سیستم بکاپ خودکار.

---

## ✨ امکانات

### 👤 پنل کاربری
- ثبت‌نام و ورود خودکار
- مشاهده موجودی کیف پول
- واریز از طریق USDT / TON / TRX
- ثبت سفارش از SMM Panel
- مشاهده تاریخچه سفارشات و واریزها

### 🛠 پنل ادمین
- مدیریت کاربران (مسدود/آزاد، تغییر موجودی)
- مدیریت سفارشات (تأیید/رد/بررسی)
- مدیریت واریزها
- آمار کامل (کاربران، سفارشات، درآمد)
- مدیریت ادمین‌ها
- تنظیمات بات (پیام خوش‌آمد، کمیسیون، حداقل واریز)
- عضویت اجباری در کانال
- پخش همگانی پیام

### 🗄 سیستم بکاپ حرفه‌ای
- بکاپ خودکار با فاصله زمانی قابل تنظیم (۱ تا ۲۴ ساعت)
- بکاپ دستی فوری
- ارسال بکاپ به گروه تلگرام
- شناسایی خودکار گروه (`/backup_id` یا Forward پیام)
- بازگردانی از فایل zip
- شامل: PostgreSQL + sessions + Redis

---

## 🏗 ساختار پروژه

```
telegram-session-bot/
├── bot/
│   ├── handlers/
│   │   ├── admin_handler.py       # پنل ادمین کامل
│   │   ├── user_handler.py        # پنل کاربری
│   │   ├── smmpass_handler.py     # جریان ثبت سفارش
│   │   ├── backup_handler.py      # سیستم بکاپ
│   │   └── force_join_handler.py  # عضویت اجباری
│   ├── services/
│   │   ├── backup_service.py      # منطق بکاپ
│   │   ├── deposit_service.py     # پردازش واریز
│   │   ├── force_join_service.py  # بررسی عضویت
│   │   ├── order_service.py       # مدیریت سفارشات
│   │   ├── settings_service.py    # تنظیمات دیتابیس
│   │   ├── smmpass.py             # اتصال به SMM Panel API
│   │   └── user_service.py        # مدیریت کاربران
│   ├── db/
│   │   ├── models.py
│   │   ├── database.py
│   │   └── migrations.sql
│   ├── middlewares/
│   │   ├── auth_middleware.py
│   │   ├── admin.py
│   │   └── flood_control.py
│   ├── main.py
│   ├── config.py
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
└── install.sh
```

---

## 🚀 نصب

### نصب خودکار (Ubuntu 22.04)

```bash
curl -fsSL https://raw.githubusercontent.com/moha100h/telegram-session-bot/main/install.sh | sudo bash
```

### نصب دستی

```bash
git clone https://github.com/moha100h/telegram-session-bot.git
cd telegram-session-bot
cp .env.example .env && nano .env
docker compose build --no-cache
docker compose up -d
docker logs tsb_bot -f
```

---

## ⚙️ متغیرهای محیطی

| متغیر | توضیح |
|-------|-------|
| `BOT_TOKEN` | توکن ربات از @BotFather |
| `ADMIN_ID` | آیدی عددی تلگرام سوپرادمین |
| `POSTGRES_DB/USER/PASSWORD` | اطلاعات دیتابیس |
| `SMM_API_URL` | آدرس API پنل SMM |
| `SMM_API_KEY` | کلید API پنل SMM |
| `USDT_WALLET` | آدرس کیف پول TRC20 |
| `TON_WALLET` | آدرس کیف پول TON |
| `TRX_WALLET` | آدرس کیف پول TRX |

---

## 🗄 راه‌اندازی بکاپ

**روش ۱ — خودکار (توصیه‌شده):**
1. بات را ادمین گروه کنید
2. پنل ادمین ← بکاپ ← «🔍 شناسایی خودکار گروه»
3. در گروه `/backup_id` بزنید
4. روی «✅ بله، تنظیم کن» کلیک کنید

**روش ۲ — Forward:**
1. پنل ادمین ← بکاپ ← «🔍 شناسایی خودکار گروه»
2. یک پیام از گروه را به بات forward کنید

---

## 🔧 دستورات مفید

```bash
# لاگ زنده
docker logs tsb_bot -f

# ریستارت
docker compose restart bot

# آپدیت
cd /opt/telegram-session-bot && git pull && docker compose build --no-cache bot && docker compose up -d

# وضعیت
docker compose ps

# پاک‌سازی دیسک
docker system prune -af
```

---

## 🛠 Stack

| ابزار | نسخه |
|-------|------|
| Python | 3.11 |
| aiogram | 3.7 |
| PostgreSQL | 15 |
| Redis | 7 |
| SQLAlchemy | 2.0 |

---

## 📄 لایسنس

MIT License
