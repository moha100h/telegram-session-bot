"""i18n v5.1 — TelegramSessionBot"""
from __future__ import annotations
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

LANGUAGES: dict[str, str] = {"en":"🇬🇧 English","fa":"🇮🇷 فارسی","ar":"🇸🇦 عربي","he":"🇮🇱 עברית","ru":"🇷🇺 Русский"}

_T: dict[str, dict[str, str]] = {
    'btn_home': {'en': '🏠 Home', 'fa': '🏠 خانه', 'ar': '🏠 الرئيسية', 'he': '🏠 בית', 'ru': '🏠 Главная'},
    'btn_back': {'en': '🔙 Back', 'fa': '🔙 بازگشت', 'ar': '🔙 رجوع', 'he': '🔙 חזרה', 'ru': '🔙 Назад'},
    'btn_cancel': {'en': '❌ Cancel', 'fa': '❌ لغو', 'ar': '❌ إلغاء', 'he': '❌ ביטול', 'ru': '❌ Отмена'},
    'btn_confirm': {'en': '✅ Confirm & Pay', 'fa': '✅ تایید و پرداخت', 'ar': '✅ تأكيد ودفع', 'he': '✅ אישור ותשלום', 'ru': '✅ Подтвердить'},
    'btn_new_order': {'en': '🛒 New Order', 'fa': '🛒 سفارش جدید', 'ar': '🛒 طلب جديد', 'he': '🛒 הזמנה חדשה', 'ru': '🛒 Новый заказ'},
    'btn_my_orders': {'en': '📦 My Orders', 'fa': '📦 سفارشات من', 'ar': '📦 طلباتي', 'he': '📦 ההזמנות שלי', 'ru': '📦 Мои заказы'},
    'btn_charge': {'en': '💳 Top Up', 'fa': '💳 شارژ موجودی', 'ar': '💳 شحن الرصيد', 'he': '💳 טעינת יתרה', 'ru': '💳 Пополнить'},
    'btn_change_lang': {'en': '🌐 Language', 'fa': '🌐 زبان', 'ar': '🌐 اللغة', 'he': '🌐 שפה', 'ru': '🌐 Язык'},
    'btn_send_hash': {'en': '✅ I Sent — Submit Hash', 'fa': '✅ واریز کردم — ارسال هش', 'ar': '✅ أرسلت — أرسل الهاش', 'he': '✅ שלחתי — שלח האש', 'ru': '✅ Отправил — Прислать хэш'},
    'btn_resend_hash': {'en': '🔄 Resend Hash', 'fa': '🔄 ارسال مجدد هش', 'ar': '🔄 إعادة إرسال الهاش', 'he': '🔄 שלח שוב האش', 'ru': '🔄 Отправить хэш снова'},
    'btn_cancel_deposit': {'en': '❌ Cancel Deposit', 'fa': '❌ لغو واریز', 'ar': '❌ إلغاء الإيداع', 'he': '❌ ביטול הפקדה', 'ru': '❌ Отменить депозит'},
    'btn_deposit_again': {'en': '💳 Deposit Again', 'fa': '💳 واریز مجدد', 'ar': '💳 إيداع مجدد', 'he': '💳 הפקד שוב', 'ru': '💳 Пополнить снова'},
    'btn_tx_history': {'en': '📋 Transactions', 'fa': '📋 تاریخچه تراکنش', 'ar': '📋 المعاملات', 'he': '📋 עסקאות', 'ru': '📋 Транзакции'},
    'btn_archive': {'en': '📜 History', 'fa': '📜 تاریخچه', 'ar': '📜 السجل', 'he': '📜 היסטוריה', 'ru': '📜 История'},
    'btn_refresh': {'en': '🔄 Refresh', 'fa': '🔄 بروزرسانی', 'ar': '🔄 تحديث', 'he': '🔄 רענן', 'ru': '🔄 Обновить'},
    'btn_prev': {'en': '◀️ Prev', 'fa': '◀️ قبلی', 'ar': '◀️ السابق', 'he': '◀️ הקודם', 'ru': '◀️ Назад'},
    'btn_next': {'en': '▶️ Next', 'fa': '▶️ بعدی', 'ar': '▶️ التالي', 'he': '▶️ הבא', 'ru': '▶️ Вперёд'},
    'btn_verify_phone': {'en': '📱 Verify Phone', 'fa': '📱 تایید شماره', 'ar': '📱 تحقق الهاتف', 'he': '📱 אמת טלפון', 'ru': '📱 Подтвердить телефон'},
    'btn_send_phone': {'en': '📱 Send Phone', 'fa': '📱 ارسال شماره', 'ar': '📱 إرسال الهاتف', 'he': '📱 שלח טלפון', 'ru': '📱 Отправить телефон'},
    'btn_support_contact': {'en': '💬 Contact Support', 'fa': '💬 ارتباط با پشتیبانی', 'ar': '💬 تواصل مع الدعم', 'he': '💬 צור קשר', 'ru': '💬 Написать в поддержку'},
    'btn_place_order': {'en': '🛒 Place Order', 'fa': '🛒 ثبت سفارش', 'ar': '🛒 تقديم الطلب', 'he': '🛒 בצע הזמנה', 'ru': '🛒 Оформить заказ'},
    'balance_label': {'en': '💰 Balance', 'fa': '💰 موجودی', 'ar': '💰 الرصيد', 'he': '💰 יתרה', 'ru': '💰 Баланс'},
    'lang_saved': {'en': '✅ Language saved', 'fa': '✅ زبان ذخیره شد', 'ar': '✅ تم حفظ اللغة', 'he': '✅ שפה נשמרה', 'ru': '✅ Язык сохранён'},
    'adm_lang_title': {'en': '🌐 Language Settings', 'fa': '🌐 تنظیمات زبان', 'ar': '🌐 إعدادات اللغة', 'he': '🌐 הגדרות שפה', 'ru': '🌐 Настройки языка'},
    'error_generic': {'en': '❌ Error', 'fa': '❌ خطا', 'ar': '❌ خطأ', 'he': '❌ שגיאה', 'ru': '❌ Ошибка'},
    'user_not_found': {'en': '❌ User not found.', 'fa': '❌ کاربر یافت نشد.', 'ar': '❌ المستخدم غير موجود.', 'he': '❌ משתמש לא נמצא.', 'ru': '❌ Пользователь не найден.'},
    'insufficient_balance': {'en': '❌ Insufficient balance.', 'fa': '❌ موجودی کافی نیست.', 'ar': '❌ رصيد غير كافٍ.', 'he': '❌ יתרה לא מספיקה.', 'ru': '❌ Недостаточно средств.'},
    'placing_order': {'en': '⏳ <b>Placing order...</b>', 'fa': '⏳ <b>در حال ثبت سفارش...</b>', 'ar': '⏳ <b>جارٍ تقديم الطلب...</b>', 'he': '⏳ <b>מבצע הזמנה...</b>', 'ru': '⏳ <b>Оформляем заказ...</b>'},
    'order_confirmed': {'en': '✅ <b>Order Placed!</b>', 'fa': '✅ <b>سفارش ثبت شد!</b>', 'ar': '✅ <b>تم تقديم الطلب!</b>', 'he': '✅ <b>ההזמנה בוצעה!</b>', 'ru': '✅ <b>Заказ оформлен!</b>'},
    'order_confirm_title': {'en': '🛒 <b>Order Confirmation</b>', 'fa': '🛒 <b>تایید سفارش</b>', 'ar': '🛒 <b>تأكيد الطلب</b>', 'he': '🛒 <b>אישור הזמנה</b>', 'ru': '🛒 <b>Подтверждение заказа</b>'},
    'order_waiting': {'en': '⏳ Your order is in queue.', 'fa': '⏳ سفارش شما در صف است.', 'ar': '⏳ طلبك في قائمة الانتظار.', 'he': '⏳ ההזמנה שלך בתור.', 'ru': '⏳ Ваш заказ в очереди.'},
    'order_bal_ok': {'en': '✅ Sufficient balance.', 'fa': '✅ موجودی کافی است.', 'ar': '✅ الرصيد كافٍ.', 'he': '✅ יתרה מספיקה.', 'ru': '✅ Баланс достаточен.'},
    'order_bal_low': {'en': '❌ Insufficient balance. Please top up.', 'fa': '❌ موجودی کافی نیست. لطفاً شارژ کنید.', 'ar': '❌ الرصيد غير كافٍ.', 'he': '❌ יתרה לא מספיקה.', 'ru': '❌ Недостаточно средств.'},
    'order_deduct_error': {'en': '❌ Balance deduction error.', 'fa': '❌ خطا در کسر موجودی.', 'ar': '❌ خطأ في خصم الرصيد.', 'he': '❌ שגיאה בניכוי יתרה.', 'ru': '❌ Ошибка списания.'},
    'order_info_missing': {'en': '❌ Order info missing.', 'fa': '❌ اطلاعات سفارش یافت نشد.', 'ar': '❌ معلومات الطلب مفقودة.', 'he': '❌ פרטי הזמנה חסרים.', 'ru': '❌ Данные заказа отсутствуют.'},
    'order_panel': {'en': 'Panel', 'fa': 'پنل', 'ar': 'اللوحة', 'he': 'פאנל', 'ru': 'Панель'},
    'order_cat': {'en': 'Category', 'fa': 'دسته', 'ar': 'الفئة', 'he': 'קטגוריה', 'ru': 'Категория'},
    'order_service': {'en': 'Service', 'fa': 'خدمت', 'ar': 'الخدمة', 'he': 'שירות', 'ru': 'Сервис'},
    'order_link_lbl': {'en': 'Link', 'fa': 'لینک', 'ar': 'الرابط', 'he': 'קישור', 'ru': 'Ссылка'},
    'order_qty_lbl': {'en': 'Quantity', 'fa': 'تعداد', 'ar': 'الكمية', 'he': 'כמות', 'ru': 'Количество'},
    'order_qty_done': {'en': '✅ Completed', 'fa': '✅ انجام شده', 'ar': '✅ مكتمل', 'he': '✅ הושלם', 'ru': '✅ Выполнено'},
    'order_note_lbl': {'en': 'Note', 'fa': 'توضیح', 'ar': 'ملاحظة', 'he': 'הערה', 'ru': 'Примечание'},
    'order_cost': {'en': 'Cost', 'fa': 'هزینه', 'ar': 'التكلفة', 'he': 'עלות', 'ru': 'Стоимость'},
    'order_paid': {'en': 'Paid', 'fa': 'پرداخت شده', 'ar': 'المدفوع', 'he': 'שולם', 'ru': 'Оплачено'},
    'order_bal_after': {'en': 'Balance after', 'fa': 'موجودی بعد', 'ar': 'الرصيد بعد', 'he': 'יתרה אחרי', 'ru': 'Баланс после'},
    'order_refund': {'en': '↩️ Refund', 'fa': '↩️ برگشت وجه', 'ar': '↩️ استرداد', 'he': '↩️ החזר', 'ru': '↩️ Возврат'},
    'order_admin_note': {'en': '📝 Admin note', 'fa': '📝 یادداشت ادمین', 'ar': '📝 ملاحظة المشرف', 'he': '📝 הערת מנהל', 'ru': '📝 Заметка админа'},
    'order_id_lbl': {'en': 'Order', 'fa': 'سفارش', 'ar': 'طلب', 'he': 'הזמנה', 'ru': 'Заказ'},
    'orders_active': {'en': '📦 <b>Active Orders</b>', 'fa': '📦 <b>سفارش\u200cهای فعال</b>', 'ar': '📦 <b>الطلبات النشطة</b>', 'he': '📦 <b>הזמנות פעילות</b>', 'ru': '📦 <b>Активные заказы</b>'},
    'orders_empty': {'en': '📦 No active orders.', 'fa': '📦 سفارش فعالی وجود ندارد.', 'ar': '📦 لا توجد طلبات نشطة.', 'he': '📦 אין הזמנות פעילות.', 'ru': '📦 Нет активных заказов.'},
    'orders_choose_panel': {'en': 'Choose a panel:', 'fa': 'یک پنل را انتخاب کنید:', 'ar': 'اختر لوحة:', 'he': 'בחר פאנל:', 'ru': 'Выберите панель:'},
    'panel_unavailable': {'en': '⚠️ Panel unavailable.', 'fa': '⚠️ پنل در دسترس نیست.', 'ar': '⚠️ اللوحة غير متاحة.', 'he': '⚠️ הפאנל אינו זמין.', 'ru': '⚠️ Панель недоступна.'},
    'panel_gone': {'en': '⚠️ Panel no longer available.', 'fa': '⚠️ پنل دیگر در دسترس نیست.', 'ar': '⚠️ اللوحة لم تعد متاحة.', 'he': '⚠️ הפאנל אינו זמין יותר.', 'ru': '⚠️ Панель больше недоступна.'},
    'cat_not_found': {'en': '❌ Category not found.', 'fa': '❌ دسته یافت نشد.', 'ar': '❌ الفئة غير موجودة.', 'he': '❌ קטגוריה לא נמצאה.', 'ru': '❌ Категория не найдена.'},
    'svc_not_found': {'en': '❌ Service not found.', 'fa': '❌ سرویس یافت نشد.', 'ar': '❌ الخدمة غير موجودة.', 'he': '❌ שירות לא נמצא.', 'ru': '❌ Сервис не найден.'},
    'svc_unavailable': {'en': '⚠️ Service unavailable.', 'fa': '⚠️ سرویس در دسترس نیست.', 'ar': '⚠️ الخدمة غير متاحة.', 'he': '⚠️ השירות אינו זמין.', 'ru': '⚠️ Сервис недоступен.'},
    'choose_category': {'en': 'Choose a category:', 'fa': 'یک دسته را انتخاب کنید:', 'ar': 'اختر فئة:', 'he': 'בחר קטגוריה:', 'ru': 'Выберите категорию:'},
    'choose_service': {'en': 'Choose a service:', 'fa': 'یک سرویس را انتخاب کنید:', 'ar': 'اختر خدمة:', 'he': 'בחר שירות:', 'ru': 'Выберите сервис:'},
    'enter_link': {'en': '🔗 Enter the link:', 'fa': '🔗 لینک را وارد کنید:', 'ar': '🔗 أدخل الرابط:', 'he': '🔗 הזן קישור:', 'ru': '🔗 Введите ссылку:'},
    'link_empty': {'en': '❌ Link cannot be empty.', 'fa': '❌ لینک نمی\u200cتواند خالی باشد.', 'ar': '❌ الرابط لا يمكن أن يكون فارغًا.', 'he': '❌ הקישור לא יכול להיות ריק.', 'ru': '❌ Ссылка не может быть пустой.'},
    'enter_note': {'en': '📝 Enter a note (or /skip):', 'fa': '📝 توضیح وارد کنید (یا /skip):', 'ar': '📝 أدخل ملاحظة (أو /skip):', 'he': '📝 הזן הערה (או /skip):', 'ru': '📝 Введите примечание (или /skip):'},
    'qty_invalid': {'en': '❌ Enter a valid number.', 'fa': '❌ عدد صحیح وارد کنید.', 'ar': '❌ أدخل رقمًا صحيحًا.', 'he': '❌ הזן מספר תקין.', 'ru': '❌ Введите корректное число.'},
    'qty_range': {'en': '❌ Qty must be {mn}–{mx}.', 'fa': '❌ تعداد باید بین {mn} و {mx} باشد.', 'ar': '❌ الكمية بين {mn} و {mx}.', 'he': '❌ כמות בין {mn} ל-{mx}.', 'ru': '❌ Кол-во от {mn} до {mx}.'},
    'enter_qty': {'en': '🔢 Qty (min:{mn} max:{mx}):', 'fa': '🔢 تعداد (حداقل:{mn} حداکثر:{mx}):', 'ar': '🔢 الكمية (الحد الأدنى:{mn} الأقصى:{mx}):', 'he': '🔢 כמות (מינ:{mn} מקס:{mx}):', 'ru': '🔢 Кол-во (мин:{mn} макс:{mx}):'},
    'smm_your_balance': {'en': '💳 Balance: <b>${bal}</b>', 'fa': '💳 موجودی: <b>${bal}</b>', 'ar': '💳 رصيدك: <b>${bal}</b>', 'he': '💳 יתרה: <b>${bal}</b>', 'ru': '💳 Баланс: <b>${bal}</b>'},
    'smm_min_max': {'en': '📊 Min:<b>{mn}</b> Max:<b>{mx}</b>', 'fa': '📊 حداقل:<b>{mn}</b> حداکثر:<b>{mx}</b>', 'ar': '📊 الأدنى:<b>{mn}</b> الأقصى:<b>{mx}</b>', 'he': '📊 מינ:<b>{mn}</b> מקס:<b>{mx}</b>', 'ru': '📊 Мин:<b>{mn}</b> Макс:<b>{mx}</b>'},
    'smm_placing': {'en': '⏳ <b>Placing order...</b>', 'fa': '⏳ <b>در حال ثبت سفارش...</b>', 'ar': '⏳ <b>جارٍ تقديم الطلب...</b>', 'he': '⏳ <b>מבצע הזמנה...</b>', 'ru': '⏳ <b>Оформляем заказ...</b>'},
    'smm_deduct_err': {'en': '❌ Deduction error.', 'fa': '❌ خطا در کسر موجودی.', 'ar': '❌ خطأ في الخصم.', 'he': '❌ שגיאה בניכוי.', 'ru': '❌ Ошибка списания.'},
    'smm_svc_not_found': {'en': '❌ Service not found!', 'fa': '❌ سرویس یافت نشد!', 'ar': '❌ الخدمة غير موجودة!', 'he': '❌ שירות לא נמצא!', 'ru': '❌ Сервис не найден!'},
    'smm_cat_not_found': {'en': '❌ Category not found!', 'fa': '❌ دسته یافت نشد!', 'ar': '❌ الفئة غير موجودة!', 'he': '❌ קטגוריה לא נמצאה!', 'ru': '❌ Категория не найдена!'},
    'smm_bal_ok': {'en': '✅ Sufficient balance.', 'fa': '✅ موجودی کافی است.', 'ar': '✅ الرصيد كافٍ.', 'he': '✅ יתרה מספיקה.', 'ru': '✅ Баланс достаточен.'},
    'smm_bal_low': {'en': '❌ Insufficient balance.', 'fa': '❌ موجودی کافی نیست.', 'ar': '❌ رصيد غير كافٍ.', 'he': '❌ יתרה לא מספيקה.', 'ru': '❌ Недостаточно средств.'},
    'smm_order_success': {'en': '✅ <b>Order Placed!</b>', 'fa': '✅ <b>سفارش ثبت شد!</b>', 'ar': '✅ <b>تم تقديم الطلب!</b>', 'he': '✅ <b>ההזמנה בוצעה!</b>', 'ru': '✅ <b>Заказ оформлен!</b>'},
    'smm_in_queue': {'en': '⏳ Order is being processed.', 'fa': '⏳ سفارش در حال پردازش است.', 'ar': '⏳ طلبك قيد المعالجة.', 'he': '⏳ ההזמנה בעיבוד.', 'ru': '⏳ Заказ обрабатывается.'},
    'smm_enter_sub': {'en': '👤 Enter username (no @):', 'fa': '👤 نام کاربری (بدون @):', 'ar': '👤 اسم المستخدم (بدون @):', 'he': '👤 שם משתמש (ללא @):', 'ru': '👤 Имя пользователя (без @):'},
    'smm_qty_empty': {'en': '❌ Value cannot be empty.', 'fa': '❌ مقدار نمی\u200cتواند خالی باشد.', 'ar': '❌ القيمة لا يمكن أن تكون فارغة.', 'he': '❌ הערך לא יכול להיות ריק.', 'ru': '❌ Значение не может быть пустым.'},
    'smm_qty_invalid': {'en': '❌ Enter a valid integer.', 'fa': '❌ عدد صحیح وارد کنید.', 'ar': '❌ أدخل رقمًا صحيحًا.', 'he': '❌ הזן מספר שלם.', 'ru': '❌ Введите целое число.'},
    'smm_qty_range': {'en': '❌ Qty must be <b>{mn}</b>–<b>{mx}</b>.', 'fa': '❌ تعداد باید بین <b>{mn}</b> و <b>{mx}</b> باشد.', 'ar': '❌ الكمية بين <b>{mn}</b> و <b>{mx}</b>.', 'he': '❌ כמות בין <b>{mn}</b> ל-<b>{mx}</b>.', 'ru': '❌ Кол-во от <b>{mn}</b> до <b>{mx}</b>.'},
    'smm_info_missing': {'en': '❌ Order info missing.', 'fa': '❌ اطلاعات سفارش یافت نشد.', 'ar': '❌ معلومات الطلب مفقودة.', 'he': '❌ פרטי הזמנה חסרים.', 'ru': '❌ Данные заказа отсутствуют.'},
    'smm_api_err': {'en': '❌ API error: <code>{err}</code>', 'fa': '❌ خطای API: <code>{err}</code>', 'ar': '❌ خطأ API: <code>{err}</code>', 'he': '❌ שגיאת API: <code>{err}</code>', 'ru': '❌ Ошибка API: <code>{err}</code>'},
    'smm_order_id': {'en': '🆔 Order: <b>#{oid}</b>', 'fa': '🆔 سفارش: <b>#{oid}</b>', 'ar': '🆔 الطلب: <b>#{oid}</b>', 'he': '🆔 הזמנה: <b>#{oid}</b>', 'ru': '🆔 Заказ: <b>#{oid}</b>'},
    'smm_api_id': {'en': '🌐 API ID: <code>{ext}</code>', 'fa': '🌐 شناسه API: <code>{ext}</code>', 'ar': '🌐 رقم API: <code>{ext}</code>', 'he': '🌐 מזהה API: <code>{ext}</code>', 'ru': '🌐 ID API: <code>{ext}</code>'},
    'smm_active_svcs': {'en': '📊 <b>{n}</b> svcs in <b>{cats}</b> cats', 'fa': '📊 <b>{n}</b> سرویس در <b>{cats}</b> دسته', 'ar': '📊 <b>{n}</b> خدمة في <b>{cats}</b> فئة', 'he': '📊 <b>{n}</b> שירותים ב-<b>{cats}</b> קטגוריות', 'ru': '📊 <b>{n}</b> сервисов в <b>{cats}</b> кат.'},
    'smm_categories': {'en': '📂 <b>Categories</b> — {p}/{total}', 'fa': '📂 <b>دسته\u200cبندی\u200cها</b> — {p}/{total}', 'ar': '📂 <b>الفئات</b> — {p}/{total}', 'he': '📂 <b>קטגוריות</b> — {p}/{total}', 'ru': '📂 <b>Категории</b> — {p}/{total}'},
    'smm_services': {'en': '📌 <b>{cat}</b> — {n} svcs ({p}/{total})', 'fa': '📌 <b>{cat}</b> — {n} سرویس ({p}/{total})', 'ar': '📌 <b>{cat}</b> — {n} خدمة ({p}/{total})', 'he': '📌 <b>{cat}</b> — {n} שירותים ({p}/{total})', 'ru': '📌 <b>{cat}</b> — {n} сервисов ({p}/{total})'},
    'smm_price_per_1k': {'en': '💰 Per 1000: <b>${p}</b>', 'fa': '💰 هر ۱۰۰۰: <b>${p}</b>', 'ar': '💰 لكل 1000: <b>${p}</b>', 'he': '💰 ל-1000: <b>${p}</b>', 'ru': '💰 За 1000: <b>${p}</b>'},
    'smm_type': {'en': '🔧 Type', 'fa': '🔧 نوع', 'ar': '🔧 النوع', 'he': '🔧 סוג', 'ru': '🔧 Тип'},
    'smm_choose_section': {'en': 'Choose a section:', 'fa': 'یک بخش را انتخاب کنید:', 'ar': 'اختر قسمًا:', 'he': 'בחר קטגוריה:', 'ru': 'Выберите раздел:'},
    'deposit_title': {'en': '💳 Deposit', 'fa': '💳 واریز موجودی', 'ar': '💳 إيداع', 'he': '💳 הפקדה', 'ru': '💳 Пополнение'},
    'deposit_coin_inactive': {'en': '❌ Currency inactive.', 'fa': '❌ این ارز فعال نیست.', 'ar': '❌ العملة غير نشطة.', 'he': '❌ מטבע לא פעיל.', 'ru': '❌ Валюта неактивна.'},
    'deposit_cancelled': {'en': '❌ Deposit cancelled.', 'fa': '❌ واریز لغو شد.', 'ar': '❌ تم إلغاء الإيداع.', 'he': '❌ ההפקדה בוטלה.', 'ru': '❌ Пополнение отменено.'},
    'deposit_hash_empty': {'en': '❌ Hash link cannot be empty.', 'fa': '❌ لینک هش نمی\u200cتواند خالی باشد.', 'ar': '❌ رابط الهاش لا يمكن أن يكون فارغًا.', 'he': '❌ קישור ההאש לא יכול להיות ריק.', 'ru': '❌ Ссылка на хэш не может быть пустой.'},
    'deposit_invalid_amount': {'en': '❌ Enter a valid amount.', 'fa': '❌ مبلغ معتبر وارد کنید.', 'ar': '❌ أدخل مبلغًا صحيحًا.', 'he': '❌ הזן סכום תקין.', 'ru': '❌ Введите корректную сумму.'},
    'deposit_price_error': {'en': '⚠️ Price fetch error.', 'fa': '⚠️ خطا در دریافت قیمت.', 'ar': '⚠️ خطأ في جلب السعر.', 'he': '⚠️ שגיאה בקבלת מחיר.', 'ru': '⚠️ Ошибка получения цены.'},
    'deposit_checking': {'en': '🔍 <b>Checking transaction...</b>', 'fa': '🔍 <b>در حال بررسی تراکنش...</b>', 'ar': '🔍 <b>جارٍ التحقق...</b>', 'he': '🔍 <b>בודק עסקה...</b>', 'ru': '🔍 <b>Проверяем транзакцию...</b>'},
    'deposit_choose_coin': {'en': 'Choose currency:', 'fa': 'ارز مورد نظر را انتخاب کنید:', 'ar': 'اختر العملة:', 'he': 'בחר מטבע:', 'ru': 'Выберите валюту:'},
    'deposit_no_method': {'en': '⚠️ No payment method active.', 'fa': '⚠️ هیچ روش پرداختی فعال نیست.', 'ar': '⚠️ لا توجد طريقة دفع نشطة.', 'he': '⚠️ אין שיטת תשלום פעילה.', 'ru': '⚠️ Нет активных методов оплаты.'},
    'deposit_enter_amount': {'en': '💵 Enter amount in USD:', 'fa': '💵 مبلغ به دلار وارد کنید:', 'ar': '💵 أدخل المبلغ بالدولار:', 'he': '💵 הזן סכום בדולר:', 'ru': '💵 Введите сумму в USD:'},
    'deposit_send_hash': {'en': '🔗 <b>Send transaction hash link:</b>', 'fa': '🔗 <b>لینک هش تراکنش را ارسال کنید:</b>', 'ar': '🔗 <b>أرسل رابط هاش المعاملة:</b>', 'he': '🔗 <b>שלח קישור לעסקה:</b>', 'ru': '🔗 <b>Отправьте ссылку на хэш:</b>'},
    'history_title': {'en': '📋 Transaction History', 'fa': '📋 تاریخچه تراکنش', 'ar': '📋 سجل المعاملات', 'he': '📋 היסטוריית עסקאות', 'ru': '📋 История транзакций'},
    'history_empty': {'en': '📋 No history yet.', 'fa': '📋 تاریخچه\u200cای وجود ندارد.', 'ar': '📋 لا يوجد سجل بعد.', 'he': '📋 אין היסטוריה עדיין.', 'ru': '📋 История пуста.'},
    'history_page': {'en': '📄 {p}/{total}', 'fa': '📄 {p}/{total}', 'ar': '📄 {p}/{total}', 'he': '📄 {p}/{total}', 'ru': '📄 {p}/{total}'},
    'support_title': {'en': '📞 <b>Support</b>', 'fa': '📞 <b>پشتیبانی</b>', 'ar': '📞 <b>الدعم</b>', 'he': '📞 <b>תמיכה</b>', 'ru': '📞 <b>Поддержка</b>'},
    'support_text': {'en': 'Choose a topic 👇', 'fa': 'یک موضوع را انتخاب کنید 👇', 'ar': 'اختر موضوعًا 👇', 'he': 'בחר נושא 👇', 'ru': 'Выберите тему 👇'},
    'profile_title': {'en': '👤 My Profile', 'fa': '👤 پروفایل من', 'ar': '👤 ملفي', 'he': '👤 הפרופיל שלי', 'ru': '👤 Мой профиль'},
    'profile_name': {'en': '🔵 Name', 'fa': '🔵 نام', 'ar': '🔵 الاسم', 'he': '🔵 שם', 'ru': '🔵 Имя'},
    'profile_username': {'en': '🔹 Username', 'fa': '🔹 یوزرنیم', 'ar': '🔹 اسم المستخدم', 'he': '🔹 שם משתמש', 'ru': '🔹 Юзернейм'},
    'profile_balance': {'en': '💰 Balance', 'fa': '💰 موجودی', 'ar': '💰 الرصيد', 'he': '💰 יתרה', 'ru': '💰 Баланс'},
    'profile_referrals': {'en': '👥 Referrals', 'fa': '👥 دعوت\u200cها', 'ar': '👥 الإحالات', 'he': '👥 הפניות', 'ru': '👥 Рефералы'},
    'profile_joined': {'en': '📅 Joined', 'fa': '📅 عضویت', 'ar': '📅 تاريخ الانضمام', 'he': '📅 הצטרף', 'ru': '📅 Дата регистрации'},
    'profile_phone_prompt': {'en': '📱 Send your phone number:', 'fa': '📱 شماره موبایل خود را ارسال کنید:', 'ar': '📱 أرسل رقم هاتفك:', 'he': '📱 שלח את מספר הטלפון שלך:', 'ru': '📱 Отправьте номер телефона:'},
    'profile_phone_ok': {'en': '📱 Phone: <b>{phone}</b> ✅', 'fa': '📱 شماره: <b>{phone}</b> ✅', 'ar': '📱 الهاتف: <b>{phone}</b> ✅', 'he': '📱 טלפון: <b>{phone}</b> ✅', 'ru': '📱 Телефон: <b>{phone}</b> ✅'},
    'profile_phone_no': {'en': '📱 Phone: ❌ Not verified', 'fa': '📱 شماره: ❌ تایید نشده', 'ar': '📱 الهاتف: ❌ غير مؤكد', 'he': '📱 טלפון: ❌ לא מאומת', 'ru': '📱 Телефон: ❌ Не подтверждён'},
    'profile_phone_saved': {'en': '✅ Phone {phone} saved!', 'fa': '✅ شماره {phone} ذخیره شد!', 'ar': '✅ تم حفظ {phone}!', 'he': '✅ {phone} נשמר!', 'ru': '✅ Телефон {phone} сохранён!'},
    'notif_order_placed': {'en': '🛒 <b>Order #{oid}</b>\n{sep}\n🏷 {panel}\n📂 {cat}\n📌 {svc}\n🔢 {qty:,}\n💰 ${amt:.4f}\n💳 ${bal:.2f}', 'fa': '🛒 <b>سفارش #{oid}</b>\n{sep}\n🏷 {panel}\n📂 {cat}\n📌 {svc}\n🔢 {qty:,}\n💰 ${amt:.4f}\n💳 ${bal:.2f}', 'ar': '🛒 <b>طلب #{oid}</b>\n{sep}\n🏷 {panel}\n📂 {cat}\n📌 {svc}\n🔢 {qty:,}\n💰 ${amt:.4f}\n💳 ${bal:.2f}', 'he': '🛒 <b>הזמנה #{oid}</b>\n{sep}\n🏷 {panel}\n📂 {cat}\n📌 {svc}\n🔢 {qty:,}\n💰 ${amt:.4f}\n💳 ${bal:.2f}', 'ru': '🛒 <b>Заказ #{oid}</b>\n{sep}\n🏷 {panel}\n📂 {cat}\n📌 {svc}\n🔢 {qty:,}\n💰 ${amt:.4f}\n💳 ${bal:.2f}'},
    'notif_status_update': {'en': '{icon} <b>Order #{oid} — {status}</b>\n{sep}\n📌 {svc}', 'fa': '{icon} <b>سفارش #{oid} — {status}</b>\n{sep}\n📌 {svc}', 'ar': '{icon} <b>طلب #{oid} — {status}</b>\n{sep}\n📌 {svc}', 'he': '{icon} <b>הזמנה #{oid} — {status}</b>\n{sep}\n📌 {svc}', 'ru': '{icon} <b>Заказ #{oid} — {status}</b>\n{sep}\n📌 {svc}'},
    'notif_refund': {'en': '↩️ <b>Refund #{oid}</b>\n{sep}\n💰 ${amt:.4f}\n💳 ${bal:.2f}\n📝 {reason}', 'fa': '↩️ <b>برگشت #{oid}</b>\n{sep}\n💰 ${amt:.4f}\n💳 ${bal:.2f}\n📝 {reason}', 'ar': '↩️ <b>استرداد #{oid}</b>\n{sep}\n💰 ${amt:.4f}\n💳 ${bal:.2f}\n📝 {reason}', 'he': '↩️ <b>החזר #{oid}</b>\n{sep}\n💰 ${amt:.4f}\n💳 ${bal:.2f}\n📝 {reason}', 'ru': '↩️ <b>Возврат #{oid}</b>\n{sep}\n💰 ${amt:.4f}\n💳 ${bal:.2f}\n📝 {reason}'},
    'notif_deposit_ok': {'en': '✅ <b>Deposit Confirmed!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'fa': '✅ <b>واریز تایید شد!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'ar': '✅ <b>تم تأكيد الإيداع!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'he': '✅ <b>ההפקדה אושרה!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'ru': '✅ <b>Пополнение подтверждено!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}'},
    'notif_deposit_rej': {'en': '❌ <b>Deposit Rejected</b>\n{sep}\n💰 ${amt:.2f}{reason}', 'fa': '❌ <b>واریز رد شد</b>\n{sep}\n💰 ${amt:.2f}{reason}', 'ar': '❌ <b>تم رفض الإيداع</b>\n{sep}\n💰 ${amt:.2f}{reason}', 'he': '❌ <b>ההפקדה נדחתה</b>\n{sep}\n💰 ${amt:.2f}{reason}', 'ru': '❌ <b>Пополнение отклонено</b>\n{sep}\n💰 ${amt:.2f}{reason}'},
    'notif_manual_charge': {'en': '🎁 <b>Manual Top-Up!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'fa': '🎁 <b>شارژ دستی!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'ar': '🎁 <b>شحن يدوي!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'he': '🎁 <b>טעינה ידנית!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}', 'ru': '🎁 <b>Ручное пополнение!</b>\n{sep}\n💰 +${amt:.2f}\n💳 ${bal:.2f}'},
}

_STATUS: dict[str, dict[str, str]] = {'pending': {'en': '⏳ Pending', 'fa': '⏳ در صف', 'ar': '⏳ قيد الانتظار', 'he': '⏳ ממתין', 'ru': '⏳ В очереди'}, 'processing': {'en': '🔄 Processing', 'fa': '🔄 در حال انجام', 'ar': '🔄 قيد المعالجة', 'he': '🔄 בעיבוד', 'ru': '🔄 В обработке'}, 'in progress': {'en': '🔄 In Progress', 'fa': '🔄 در حال انجام', 'ar': '🔄 قيد التنفيذ', 'he': '🔄 בתהליך', 'ru': '🔄 Выполняется'}, 'completed': {'en': '✅ Completed', 'fa': '✅ تکمیل شده', 'ar': '✅ مكتمل', 'he': '✅ הושלם', 'ru': '✅ Выполнен'}, 'partial': {'en': '⚠️ Partial', 'fa': '⚠️ ناقص', 'ar': '⚠️ جزئي', 'he': '⚠️ חלקי', 'ru': '⚠️ Частичный'}, 'cancelled': {'en': '❌ Cancelled', 'fa': '❌ کنسل شده', 'ar': '❌ ملغى', 'he': '❌ בוטל', 'ru': '❌ Отменён'}, 'canceled': {'en': '❌ Cancelled', 'fa': '❌ کنسل شده', 'ar': '❌ ملغى', 'he': '❌ בוטل', 'ru': '❌ Отменён'}, 'failed': {'en': '💔 Failed', 'fa': '💔 ناموفق', 'ar': '💔 فشل', 'he': '💔 נכשל', 'ru': '💔 Ошибка'}, 'refunded': {'en': '↩️ Refunded', 'fa': '↩️ برگشت خورده', 'ar': '↩️ مسترد', 'he': '↩️ הוחזר', 'ru': '↩️ Возвращён'}, 'rejected': {'en': '❌ Rejected', 'fa': '❌ رد شده', 'ar': '❌ مرفوض', 'he': '❌ נדחה', 'ru': '❌ Отклонён'}, 'approved': {'en': '✅ Approved', 'fa': '✅ تایید شده', 'ar': '✅ موافق عليه', 'he': '✅ אושר', 'ru': '✅ Одобрен'}}

def t(key: str, lang: str = "en", **kwargs) -> str:
    lang = lang if lang in LANGUAGES else "en"
    row  = _T.get(key, {})
    text = row.get(lang) or row.get("en") or key
    if kwargs:
        try: text = text.format(**kwargs)
        except (KeyError, ValueError): pass
    return text

def status_label(status: str, lang: str = "en") -> str:
    lang = lang if lang in LANGUAGES else "en"
    row  = _STATUS.get((status or "").lower(), {})
    return row.get(lang) or row.get("en") or status

def lang_keyboard(active_langs: list | None = None) -> InlineKeyboardMarkup:
    langs = active_langs or list(LANGUAGES.keys())
    rows, row = [], []
    for code in langs:
        if code not in LANGUAGES: continue
        row.append(InlineKeyboardButton(text=LANGUAGES[code], callback_data=f"set_lang_{code}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)