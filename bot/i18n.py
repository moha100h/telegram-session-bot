"""i18n — Multi-language: en, fa, ar, he, ru"""
from typing import Dict

LANGUAGES: Dict[str, str] = {
    "en": "🇬🇧 English",
    "fa": "🇮🇷 فارسی",
    "ar": "🇸🇦 العربية",
    "he": "🇮🇱 עברית",
    "ru": "🇷🇺 Русский",
}

_T: Dict[str, Dict[str, str]] = {
    "btn_wallet":           {"en":"💳 Wallet",           "fa":"💳 کیف پول",          "ar":"💳 المحفظة",         "he":"💳 ארנק",            "ru":"💳 Кошелёк"},
    "btn_orders":           {"en":"📦 My Orders",        "fa":"📦 سفارش‌هایم",       "ar":"📦 طلباتي",          "he":"📦 ההזמנות שלי",     "ru":"📦 Мои заказы"},
    "btn_support":          {"en":"🎧 Support",          "fa":"🎧 پشتیبانی",         "ar":"🎧 الدعم",           "he":"🎧 תמיכה",           "ru":"🎧 Поддержка"},
    "btn_profile":          {"en":"👤 Profile",          "fa":"👤 پروفایل",          "ar":"👤 ملفي",            "he":"👤 פרופיל",          "ru":"👤 Профиль"},
    "btn_back":             {"en":"🔙 Back",             "fa":"🔙 بازگشت",           "ar":"🔙 رجوع",            "he":"🔙 חזרה",            "ru":"🔙 Назад"},
    "btn_home":             {"en":"🏠 Home",             "fa":"🏠 خانه",             "ar":"🏠 الرئيسية",        "he":"🏠 בית",             "ru":"🏠 Главная"},
    "btn_deposit":          {"en":"💰 Deposit",          "fa":"💰 واریز",            "ar":"💰 إيداع",           "he":"💰 הפקדה",           "ru":"💰 Пополнить"},
    "btn_history":          {"en":"📜 History",          "fa":"📜 تاریخچه",          "ar":"📜 السجل",           "he":"📜 היסטוריה",        "ru":"📜 История"},
    "btn_cancel":           {"en":"❌ Cancel",           "fa":"❌ لغو",              "ar":"❌ إلغاء",           "he":"❌ ביטול",           "ru":"❌ Отмена"},
    "btn_confirm":          {"en":"✅ Confirm",          "fa":"✅ تأیید",            "ar":"✅ تأكيد",           "he":"✅ אישור",           "ru":"✅ Подтвердить"},
    "btn_change_lang":      {"en":"🌐 Language",         "fa":"🌐 زبان",             "ar":"🌐 اللغة",           "he":"🌐 שפה",             "ru":"🌐 Язык"},
    "btn_join_channel":     {"en":"📢 Join Channel",     "fa":"📢 عضویت در کانال",   "ar":"📢 انضم للقناة",     "he":"📢 הצטרף לערוץ",     "ru":"📢 Вступить в канал"},
    "btn_verify_join":      {"en":"✅ I Joined",         "fa":"✅ عضو شدم",          "ar":"✅ انضممت",          "he":"✅ הצטרפתי",         "ru":"✅ Я вступил"},
    "btn_transactions":     {"en":"📋 Transactions",     "fa":"📋 تراکنش‌ها",        "ar":"📋 المعاملات",       "he":"📋 עסקאות",          "ru":"📋 Транзакции"},
    "btn_refresh":          {"en":"🔄 Refresh",          "fa":"🔄 بروزرسانی",        "ar":"🔄 تحديث",           "he":"🔄 רענן",            "ru":"🔄 Обновить"},
    "btn_new_order":        {"en":"🛒 New Order",        "fa":"🛒 سفارش جدید",       "ar":"🛒 طلب جديد",        "he":"🛒 הזמנה חדשה",      "ru":"🛒 Новый заказ"},
    "lang_saved":           {"en":"✅ English selected!","fa":"✅ فارسی انتخاب شد!","ar":"✅ تم اختيار العربية!","he":"✅ עברית נבחרה!",   "ru":"✅ Русский выбран!"},
    "choose_section":       {"en":"Choose a section:",  "fa":"یک بخش را انتخاب کنید:","ar":"اختر قسماً:",      "he":"בחר קטגוריה:",       "ru":"Выберите раздел:"},
    "balance_label":        {"en":"💰 Balance",          "fa":"💰 موجودی",           "ar":"💰 الرصيد",          "he":"💰 יתרה",            "ru":"💰 Баланс"},
    "fj_joined":            {"en":"✅ Membership verified!","fa":"✅ عضویت تأیید شد!","ar":"✅ تم التحقق من العضوية!","he":"✅ החברות אומתה!","ru":"✅ Членство подтверждено!"},
    "fj_not_joined":        {"en":"❌ You haven't joined yet!","fa":"❌ هنوز عضو نشده‌اید!","ar":"❌ لم تنضم بعد!","he":"❌ עדיין לא הצטרפת!","ru":"❌ Вы ещё не вступили!"},
    "orders_active":        {"en":"📦 <b>Active Orders</b>","fa":"📦 <b>سفارش‌های فعال</b>","ar":"📦 <b>الطلبات النشطة</b>","he":"📦 <b>הזמנות פעילות</b>","ru":"📦 <b>Активные заказы</b>"},
    "orders_empty":         {"en":"📦 No active orders.","fa":"📦 سفارش فعالی وجود ندارد.","ar":"📦 لا توجد طلبات نشطة.","he":"📦 אין הזמנות פעילות.","ru":"📦 Нет активных заказов."},
    "history_title":        {"en":"📜 <b>Order History</b>","fa":"📜 <b>تاریخچه سفارشات</b>","ar":"📜 <b>سجل الطلبات</b>","he":"📜 <b>היסטוריית הזמנות</b>","ru":"📜 <b>История заказов</b>"},
    "history_empty":        {"en":"📜 History is empty.","fa":"📜 تاریخچه خالی است.","ar":"📜 السجل فارغ.","he":"📜 ההיסטוריה ריקה.","ru":"📜 История пуста."},
    "history_page":         {"en":"Page {p}/{total}","fa":"صفحه {p}/{total}","ar":"صفحة {p}/{total}","he":"עמוד {p}/{total}","ru":"Страница {p}/{total}"},
    "support_title":        {"en":"🎧 <b>Support</b>","fa":"🎧 <b>پشتیبانی</b>","ar":"🎧 <b>الدعم</b>","he":"🎧 <b>תמיכה</b>","ru":"🎧 <b>Поддержка</b>"},
    "support_text":         {"en":"Send your message:","fa":"پیام خود را ارسال کنید:","ar":"أرسل رسالتك:","he":"שלח את הודעתך:","ru":"Отправьте сообщение:"},
    "banned_msg":           {"en":"⛔️ Your account is banned.","fa":"⛔️ حساب شما مسدود شده است.","ar":"⛔️ حسابك محظور.","he":"⛔️ חשבונך חסום.","ru":"⛔️ Ваш аккаунт заблокирован."},
    "error_generic":        {"en":"❌ An error occurred.","fa":"❌ خطایی رخ داد.","ar":"❌ حدث خطأ.","he":"❌ אירעה שגיאה.","ru":"❌ Произошла ошибка."},
    "status_pending":       {"en":"⏳ Pending",   "fa":"⏳ در صف",         "ar":"⏳ قيد الانتظار","he":"⏳ ממתין",   "ru":"⏳ В очереди"},
    "status_processing":    {"en":"🔄 Processing","fa":"🔄 در حال انجام",  "ar":"🔄 قيد التنفيذ", "he":"🔄 בעיבוד",  "ru":"🔄 В обработке"},
    "status_completed":     {"en":"✅ Completed", "fa":"✅ تکمیل شده",     "ar":"✅ مكتمل",        "he":"✅ הושלם",    "ru":"✅ Выполнен"},
    "status_partial":       {"en":"⚠️ Partial",  "fa":"⚠️ ناقص",         "ar":"⚠️ جزئي",         "he":"⚠️ חלקי",    "ru":"⚠️ Частичный"},
    "status_cancelled":     {"en":"❌ Cancelled", "fa":"❌ کنسل شده",      "ar":"❌ ملغى",          "he":"❌ בוטל",     "ru":"❌ Отменён"},
    "status_failed":        {"en":"💔 Failed",    "fa":"💔 ناموفق",        "ar":"💔 فاشل",          "he":"💔 נכשל",     "ru":"💔 Неудача"},
    "status_refunded":      {"en":"↩️ Refunded", "fa":"↩️ برگشت خورده",  "ar":"↩️ مسترد",         "he":"↩️ הוחזר",   "ru":"↩️ Возврат"},
    "order_confirmed":      {"en":"✅ <b>Order Confirmed!</b>","fa":"✅ <b>سفارش ثبت شد!</b>","ar":"✅ <b>تم تأكيد الطلب!</b>","he":"✅ <b>ההזמנה אושרה!</b>","ru":"✅ <b>Заказ подтверждён!</b>"},
    "insufficient_balance": {"en":"❌ Insufficient balance.","fa":"❌ موجودی کافی نیست.","ar":"❌ رصيد غير كافٍ.","he":"❌ יתרה לא מספיקה.","ru":"❌ Недостаточно средств."},
    "panel_unavailable":    {"en":"❌ Panel not available.","fa":"❌ این پنل در دسترس نیست.","ar":"❌ اللوحة غير متاحة.","he":"❌ פאנל לא זמין.","ru":"❌ Панель недوступна."},
    "choose_category":      {"en":"Choose a category:","fa":"یک دسته‌بندی را انتخاب کنید:","ar":"اختر فئة:","he":"בחר קטגוריה:","ru":"Выберите категорию:"},
    "choose_service":       {"en":"Choose a service:","fa":"یک خدمت را انتخاب کنید:","ar":"اختر خدمة:","he":"בחר שירות:","ru":"Выберите услугу:"},
    "enter_link":           {"en":"🔗 Enter the target link:","fa":"🔗 لینک مقصد را وارد کنید:","ar":"🔗 أدخل الرابط:","he":"🔗 הזן את הקישור:","ru":"🔗 Введите ссылку:"},
    "enter_qty":            {"en":"🔢 Enter quantity ({mn}–{mx}):","fa":"🔢 تعداد را وارد کنید ({mn}–{mx}):","ar":"🔢 أدخل الكمية ({mn}–{mx}):","he":"🔢 הזן כמות ({mn}–{mx}):","ru":"🔢 Введите количество ({mn}–{mx}):"},
    "admin_panel_btn":      {"en":"🔧 Admin Panel","fa":"🔧 پنل مدیریت","ar":"🔧 لوحة الإدارة","he":"🔧 פאנל ניהול","ru":"🔧 Панель администратора"},
    "user_panel_btn":       {"en":"👤 User Panel","fa":"👤 پنل کاربری","ar":"👤 لوحة المستخدم","he":"👤 פאנל משתמש","ru":"👤 Панель пользователя"},
    "adm_lang_title":       {"en":"🌐 Language Settings","fa":"🌐 تنظیمات زبان","ar":"🌐 إعدادات اللغة","he":"🌐 הגדרות שפה","ru":"🌐 Настройки языка"},
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    entry = _T.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def lang_keyboard(active_langs=None):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    if active_langs is None:
        active_langs = list(LANGUAGES.keys())
    rows, row = [], []
    for code, label in LANGUAGES.items():
        if code not in active_langs:
            continue
        row.append(InlineKeyboardButton(text=label, callback_data=f"set_lang_{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
