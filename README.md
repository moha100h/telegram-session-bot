# 🚀 Telegram SMM Panel Bot

A professional Telegram bot for SMM (Social Media Marketing) services powered by [SMMPass](https://smmpass.com).

---

## ✨ Features

### 👤 User Panel
| Feature | Description |
|---|---|
| 🛒 SMM Orders | Browse categories with pagination, view **raw API prices** (no hidden markup) |
| 💰 Wallet | Deposit via USDT/TON/TRX, view transaction history |
| 📦 My Orders | Track all orders with live status icons |
| 🔍 Order Status | Check any order by API ID |
| 👤 Profile | Balance, referral stats, phone verification |
| 📞 Support | Configurable support link |

### 🔧 Admin Panel
| Feature | Description |
|---|---|
| 💳 Deposits | Approve/reject with **instant user notification** |
| 👥 Users | Search, view details, ban/unban, manual credit |
| 📦 Orders | View all orders with status |
| 🚀 SMMPass | API balance, categories with profit margins, cache refresh |
| ⚙️ Settings | Bot name, welcome message, wallet addresses, **SMM button name**, profit % |
| 📢 Broadcast | Send message to all users |
| 📊 Stats | Users, orders, revenue overview |

---

## 🛠 Tech Stack

- **Python 3.11** + **aiogram 3.x**
- **PostgreSQL** + SQLAlchemy async
- **Redis** (FSM storage)
- **Docker Compose**
- **SMMPass API** (httpx async client)

---

## 🚀 Quick Start

```bash
git clone https://github.com/moha100h/telegram-session-bot
cd telegram-session-bot
cp .env.example .env
# Edit .env with your values
docker compose up -d --build
```

---

## ⚙️ Environment Variables

```env
BOT_TOKEN=your_bot_token
ADMIN_ID=your_telegram_id
SMMPASS_KEY=your_smmpass_api_key
DATABASE_URL=postgresql+asyncpg://smm:smm123@postgres:5432/smmbot
REDIS_URL=redis://redis:6379/0
```

---

## 📁 Project Structure

```
bot/
├── handlers/
│   ├── admin_handler.py      # Full admin panel (deposits, users, settings, SMMPass)
│   ├── user_handler.py       # User panel (wallet, deposit, orders, support)
│   └── smmpass_handler.py    # SMM ordering flow (categories → service → confirm → pay)
├── services/
│   ├── smmpass.py            # SMMPass API client (raw prices, 1h cache)
│   ├── deposit_service.py    # Deposit management (create, approve, reject)
│   ├── order_service.py      # Order management
│   ├── user_service.py       # User management (balance, ban, admin check)
│   └── settings_service.py   # Bot settings (get/set AdminSetting)
├── db/
│   ├── models.py             # SQLAlchemy models
│   └── database.py           # Async DB connection
└── middlewares/
    └── auth_middleware.py    # Auto-register users + ban check
```

---

## 💡 Key Design Decisions

- **Raw prices for users** — prices shown in SMM panel are direct API prices, no markup added
- **Profit tracking** — admin sets markup % for internal reporting only
- **SMM button name** — configurable from admin settings (`smm_panel_title` key)
- **Deposit flow** — manual approval with automatic Telegram notification to user
- **FSM safety** — all order states validated, `/cancel` works at every step
- **Pagination** — categories (5/page) and services (6/page) with prev/next navigation

---

## 🔑 Admin Commands

| Command | Description |
|---|---|
| `/start` | Main menu (shows admin panel button if admin) |
| `/admin` | Direct link to admin panel |
| `/balance` | Quick balance check |
| `/orders` | Quick orders view |
