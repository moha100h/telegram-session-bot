# 🤖 Telegram Session Bot

سیستم پیشرفته مدیریت سشن تلگرام — فقط بات ادمین، بدون پنل وب.

## ✨ امکانات

- 📱 **مدیریت سشن** — آپلود، بررسی، حذف سشن‌های `.session`
- 📲 **شماره مجازی** — دریافت کد تلگرام و ذخیره سشن مستقیم از بات
- 🤖 **پروفایل خودکار** — نام، نام‌خانوادگی، بیو، یوزرنیم، عکس پروفایل رندوم
- 📥 **تسک عضویت** — عضویت انبوه در کانال/گروه
- 🔄 **گروه به گروه** — انتقال اعضا از گروه مبدأ به مقصد (هر سشن ۱۰-۵۰ نفر)
- 👁 **ویو پست** — افزایش بازدید پست کانال
- 👍 **ری‌اکشن** — ری‌اکشن انبوه روی پست
- 🌐 **پروکسی خودکار** — دریافت و بروزرسانی خودکار پروکسی از اینترنت
- 📊 **آمار کامل** — آمار سشن‌ها، تسک‌ها، پروکسی‌ها
- 🗄 **بکاپ خودکار** — هر ۱ ساعت بکاپ به ادمین ارسال می‌شود
- 📥 **بازگردانی بکاپ** — آپلود فایل zip و بازگردانی خودکار

---

## 🚀 نصب روی سرور لینوکس (Ubuntu 22.04)

### ۱. نصب Docker

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
```

### ۲. دانلود پروژه

```bash
apt install git -y
git clone https://github.com/moha100h/telegram-session-bot.git
cd telegram-session-bot
```

### ۳. ساخت فایل .env

```bash
cp .env.example .env
nano .env
```

مقادیر زیر را پر کنید:

```env
BOT_TOKEN=توکن_بات_از_BotFather
ADMIN_IDS=آیدی_عددی_ادمین
API_ID=آیدی_از_my.telegram.org
API_HASH=هش_از_my.telegram.org
```

### ۴. ساخت پوشه‌های لازم

```bash
mkdir -p sessions backups data
```

### ۵. اجرا

```bash
docker compose up -d --build
```

### ۶. بررسی وضعیت

```bash
docker compose ps
docker compose logs -f bot
```

---

## 📋 دستورات مفید

```bash
# مشاهده لاگ بات
docker compose logs -f bot

# مشاهده لاگ worker
docker compose logs -f worker

# ری‌استارت
docker compose restart

# آپدیت از GitHub
git pull && docker compose up -d --build

# توقف
docker compose down
```

---

## 📱 راهنمای استفاده

۱. بات را در تلگرام باز کنید و `/start` بزنید
۲. از منوی **سشن‌ها** فایل `.session` آپلود کنید یا از **شماره مجازی** سشن جدید بسازید
۳. از منوی **تسک‌ها** نوع عملیات را انتخاب کنید
۴. آمار را از منوی **آمار** ببینید

---

## 🏗 ساختار پروژه

```
telegram-session-bot/
├── bot/                    # بات تلگرام (aiogram)
│   ├── handlers/           # هندلرهای دستورات
│   ├── services/           # سرویس‌های اصلی
│   ├── middlewares/        # میدلور ادمین
│   ├── main.py
│   ├── config.py
│   ├── Dockerfile
│   └── requirements.txt
├── worker/                 # اجراکننده تسک‌ها (Telethon)
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── sessions/               # فایل‌های .session (auto-created)
├── data/                   # دیتا JSON (auto-created)
├── backups/                # بکاپ‌ها (auto-created)
├── docker-compose.yml
└── .env
```

---

## ⚠️ نکات مهم

- فایل `.env` را هرگز در گیت‌هاب آپلود نکنید
- پوشه `sessions/` حاوی اطلاعات حساس است — بکاپ بگیرید
- برای هر سشن یک پروکسی رندوم از لیست انتخاب می‌شود
- بکاپ خودکار هر ۱ ساعت به ادمین ارسال می‌شود
