"""
Order Polling Service
هر 5 دقیقه سفارشات pending/processing رو از SmmPass API چک میکنه
و در صورت تغییر وضعیت، کاربر رو نوتیف میده.
"""
import asyncio
import logging
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import Order, User
from services.smmpass import get_order_status
from services.notification_service import notify_order_status, notify_refund

logger = logging.getLogger("order_polling")

POLL_INTERVAL = 300  # هر 5 دقیقه
ACTIVE_STATUSES = ("pending", "processing", "in progress")

STATUS_FA = {
    "pending":     "در صف",
    "processing":  "در حال انجام",
    "in progress": "در حال انجام",
    "completed":   "تکمیل شده",
    "partial":     "ناقص",
    "cancelled":   "کنسل شده",
}


async def _process_refund(session, order: Order, live_status: str, data: dict) -> float:
    """محاسبه و اعمال برگشت وجه برای partial/cancelled"""
    refund = 0.0
    if live_status == "cancelled":
        refund = order.sell_price
    elif live_status == "partial":
        remains = int(data.get("remains", 0))
        if remains > 0 and order.quantity > 0:
            refund = round(order.sell_price * remains / order.quantity, 4)

    if refund > 0:
        result = await session.execute(
            select(User).where(User.id == order.user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.balance = round((user.balance or 0) + refund, 4)
            await session.flush()

    return refund


async def poll_orders(bot) -> None:
    """یک دور چک کردن همه سفارشات فعال"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(
                Order.status.in_(ACTIVE_STATUSES),
                Order.api_order_id.isnot(None),
            )
        )
        orders = result.scalars().all()

        if not orders:
            return

        logger.info(f"Polling {len(orders)} active SmmPass orders...")

        for order in orders:
            try:
                data = await get_order_status(int(order.api_order_id))
                live_status = str(data.get("status", "")).lower().strip()

                if not live_status or live_status == order.status:
                    continue

                old_status = order.status
                order.status = live_status

                start_count = data.get("start_count")
                remains = data.get("remains")
                if start_count is not None:
                    try: order.start_count = int(start_count)
                    except: pass
                if remains is not None:
                    try: order.remains = int(remains)
                    except: pass

                refund = 0.0
                if live_status in ("cancelled", "partial") and old_status not in ("cancelled", "partial"):
                    refund = await _process_refund(session, order, live_status, data)

                await session.flush()

                user_result = await session.execute(
                    select(User).where(User.id == order.user_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    continue

                completed_qty = None
                if live_status == "partial" and order.remains is not None:
                    completed_qty = order.quantity - order.remains

                await notify_order_status(
                    bot,
                    user.telegram_id,
                    order_id=order.id,
                    service_name=order.service_name or "",
                    status=live_status,
                    quantity=order.quantity,
                    completed_qty=completed_qty,
                    refund=refund,
                )

                if refund > 0:
                    new_balance = round((user.balance or 0), 4)
                    await notify_refund(
                        bot,
                        user.telegram_id,
                        amount=refund,
                        order_id=order.id,
                        reason=f"سفارش {STATUS_FA.get(live_status, live_status)}",
                        balance=new_balance,
                    )

                logger.info(
                    f"Order #{order.id} (api:{order.api_order_id}): "
                    f"{old_status} -> {live_status}"
                    + (f" | refund=${refund}" if refund else "")
                )

            except Exception as e:
                logger.warning(f"Error polling order #{order.id}: {e}")
                continue

        await session.commit()


async def start_order_polling(bot) -> None:
    """Background task — اجرا میشه از main.py"""
    logger.info("Order polling service started.")
    while True:
        try:
            await poll_orders(bot)
        except Exception as e:
            logger.error(f"Polling loop error: {e}")
        await asyncio.sleep(POLL_INTERVAL)
