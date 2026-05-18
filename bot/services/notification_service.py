"""
Notification service
"""
from __future__ import annotations
import logging

logger = logging.getLogger("notif")

STATUS_ICONS = {
    "pending":    "⏳",
    "processing": "🔄",
    "completed":  "✅",
    "partial":    "⚠️",
    "rejected":   "❌",
}
STATUS_FA = {
    "pending":    "در صف",
    "processing": "در حال انجام",
    "completed":  "تکمیل شد",
    "partial":    "تکمیل جزئی",
    "rejected":   "رد شد",
}


async def notify_user(bot, telegram_id: int, text: str):
    try:
        await bot.send_message(telegram_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"notify_user {telegram_id}: {e}")


async def notify_order_confirmed(
    bot, telegram_id: int,
    order_id: int, panel_name: str, service_name: str,
    quantity: int, amount: float, balance: float,
):
    """ثبت سفارش + کسر موجودی در یک پیام"""
    sep = "━" * 24
    await notify_user(bot, telegram_id,
        f"⏳ <b>سفارش #{order_id} ثبت شد</b>\n"
        f"{sep}\n"
        f"🏷 پنل: <b>{panel_name}</b>\n"
        f"📌 خدمت: <b>{service_name[:40]}</b>\n"
        f"🔢 تعداد: <b>{quantity:,}</b>\n"
        f"💸 پرداخت: <b>${amount:.4f}</b>  |  💳 موجودی: <b>${balance:.2f}</b>"
    )


async def notify_order_status(
    bot, telegram_id: int, order_id: int,
    service_name: str, status: str,
    quantity: int = 0, completed_qty: int = None,
    refund: float = 0.0, admin_note: str = "",
):
    icon      = STATUS_ICONS.get(status, "📌")
    status_fa = STATUS_FA.get(status, status)
    sep = "━" * 24
    text = (
        f"{icon} <b>سفارش #{order_id} — {status_fa}</b>\n"
        f"{sep}\n"
        f"📌 {service_name[:40]}\n"
    )
    if completed_qty is not None and status == "partial":
        text += f"✅ انجام شده: <b>{completed_qty:,}</b>\n"
    if refund > 0:
        text += f"↩️ بازگشت: <b>${refund:.4f}</b>\n"
    if admin_note:
        text += f"📝 {admin_note}\n"
    await notify_user(bot, telegram_id, text)


async def notify_refund(bot, telegram_id: int, amount: float,
                         order_id: int, reason: str, balance: float):
    sep = "━" * 24
    await notify_user(bot, telegram_id,
        f"↩️ <b>بازگشت وجه — سفارش #{order_id}</b>\n"
        f"{sep}\n"
        f"💰 <b>${amount:.4f}</b>  |  💳 موجودی: <b>${balance:.2f}</b>\n"
        f"📌 {reason}"
    )


async def notify_deposit_approved(bot, telegram_id: int, amount: float,
                                   method: str = "", balance: float = 0.0):
    sep = "━" * 24
    await notify_user(bot, telegram_id,
        f"✅ <b>شارژ تایید شد</b>\n"
        f"{sep}\n"
        f"💰 <b>${amount:.2f}</b>  |  💳 موجودی: <b>${balance:.2f}</b>"
    )


async def notify_deposit_rejected(bot, telegram_id: int, amount: float, reason: str = ""):
    sep = "━" * 24
    await notify_user(bot, telegram_id,
        f"❌ <b>شارژ رد شد</b>\n"
        f"{sep}\n"
        f"💰 <b>${amount:.2f}</b>"
        + (f"\n📝 {reason}" if reason else "")
    )


async def notify_manual_credit(bot, telegram_id: int, amount: float,
                                by_admin: str, balance: float):
    sep = "━" * 24
    await notify_user(bot, telegram_id,
        f"🎁 <b>شارژ دستی</b>\n"
        f"{sep}\n"
        f"💰 <b>${amount:.2f}</b>  |  💳 موجودی: <b>${balance:.2f}</b>"
    )


# backward compat — حذف شده
async def notify_balance_deducted(bot, telegram_id: int, amount: float,
                                   reason: str, balance: float):
    pass
