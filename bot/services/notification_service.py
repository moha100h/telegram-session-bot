"""
Notification service — send user notifications for all transaction types.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("notif")

STATUS_ICONS = {
    "pending":    "⏳",
    "processing": "🔄",
    "completed":  "✅",
    "partial":    "⚠️",
    "rejected":   "❌",
}

async def notify_user(bot, telegram_id: int, text: str):
    """ارسال پیام به کاربر — خطا رو نادیده می‌گیره"""
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"notify_user {telegram_id}: {e}")


async def notify_deposit_approved(bot, telegram_id: int, amount: float,
                                   method: str = "", balance: float = 0.0):
    await notify_user(bot, telegram_id,
        f"✅ <b>شارژ موجودی تایید شد</b>\n"
        f"{'━'*28}\n"
        f"💰 مبلغ: <b>${amount:.2f}</b>\n"
        f"💳 روش: <b>{method or 'دستی'}</b>\n"
        f"👛 موجودی جدید: <b>${balance:.2f}</b>"
    )


async def notify_deposit_rejected(bot, telegram_id: int, amount: float, reason: str = ""):
    await notify_user(bot, telegram_id,
        f"❌ <b>شارژ موجودی رد شد</b>\n"
        f"{'━'*28}\n"
        f"💰 مبلغ: <b>${amount:.2f}</b>\n"
        + (f"📝 دلیل: {reason}\n" if reason else "") +
        f"\nبرای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
    )


async def notify_order_status(bot, telegram_id: int, order_id: int,
                               service_name: str, status: str,
                               quantity: int = 0, completed_qty: int = None,
                               refund: float = 0.0, admin_note: str = ""):
    icon = STATUS_ICONS.get(status, "📌")
    status_fa = {
        "pending":    "در انتظار",
        "processing": "در حال انجام",
        "completed":  "تکمیل شد",
        "partial":    "تکمیل جزئی",
        "rejected":   "رد شد",
    }.get(status, status)

    text = (
        f"{icon} <b>سفارش #{order_id} — {status_fa}</b>\n"
        f"{'━'*28}\n"
        f"🛒 خدمت: <b>{service_name[:50]}</b>\n"
    )
    if quantity:
        text += f"🔢 تعداد: <b>{quantity:,}</b>\n"
    if completed_qty is not None and status == "partial":
        text += f"✅ انجام شده: <b>{completed_qty:,}</b>\n"
    if refund > 0:
        text += f"↩️ بازگشت وجه: <b>${refund:.4f}</b>\n"
    if admin_note:
        text += f"📝 یادداشت: <i>{admin_note}</i>\n"

    await notify_user(bot, telegram_id, text)


async def notify_balance_deducted(bot, telegram_id: int, amount: float,
                                   reason: str, balance: float):
    await notify_user(bot, telegram_id,
        f"💸 <b>کسر موجودی</b>\n"
        f"{'━'*28}\n"
        f"💰 مبلغ: <b>${amount:.4f}</b>\n"
        f"📌 بابت: <i>{reason}</i>\n"
        f"👛 موجودی باقی‌مانده: <b>${balance:.2f}</b>"
    )


async def notify_refund(bot, telegram_id: int, amount: float,
                         order_id: int, reason: str, balance: float):
    await notify_user(bot, telegram_id,
        f"↩️ <b>بازگشت وجه</b>\n"
        f"{'━'*28}\n"
        f"💰 مبلغ: <b>${amount:.4f}</b>\n"
        f"🆔 سفارش: <b>#{order_id}</b>\n"
        f"📌 دلیل: <i>{reason}</i>\n"
        f"👛 موجودی جدید: <b>${balance:.2f}</b>"
    )


async def notify_manual_credit(bot, telegram_id: int, amount: float,
                                by_admin: str, balance: float):
    await notify_user(bot, telegram_id,
        f"🎁 <b>شارژ دستی موجودی</b>\n"
        f"{'━'*28}\n"
        f"💰 مبلغ: <b>${amount:.2f}</b>\n"
        f"👤 توسط: <i>{by_admin}</i>\n"
        f"👛 موجودی جدید: <b>${balance:.2f}</b>"
    )
