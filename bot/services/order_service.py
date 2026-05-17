"""
Order service - place and manage SMM orders.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Order, AdminSetting

logger = logging.getLogger("order_service")


async def get_markup(session: AsyncSession) -> float:
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.key == "smm_markup_percent")
    )
    row = result.scalar_one_or_none()
    try:
        return float(row.value) if row and row.value else 20.0
    except Exception:
        return 20.0


def apply_markup(price: float, markup_percent: float) -> float:
    return round(price * (1 + markup_percent / 100), 4)


def calc_order_price(rate: float, quantity: int, markup_percent: float) -> float:
    base = rate * quantity / 1000
    return round(base * (1 + markup_percent / 100), 4)


async def create_order(
    session: AsyncSession,
    user_id: int,
    service_id: int,
    service_name: str,
    link: str,
    quantity: int,
    cost_price: float,
    sell_price: float,
    api_order_id: str = None,
) -> Order:
    order = Order(
        user_id      = user_id,
        service_id   = service_id,
        service_name = service_name,
        link         = link,
        quantity     = quantity,
        cost_price   = cost_price,
        sell_price   = sell_price,
        status       = "pending",
        api_order_id = api_order_id,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def place_order(
    session: AsyncSession,
    user_id: int,
    service_id: int,
    service_name: str,
    link: str,
    quantity: int,
    cost_price: float,
    sell_price: float,
    api_order_id: str = None,
) -> Order:
    return await create_order(
        session, user_id, service_id, service_name,
        link, quantity, cost_price, sell_price,
        api_order_id=api_order_id,
    )


async def get_user_orders(session: AsyncSession, user_id: int) -> list:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all_orders(session: AsyncSession) -> list:
    result = await session.execute(
        select(Order).order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order).where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def update_order_status(
    session: AsyncSession,
    order_id: int,
    status: str,
    start_count: int = None,
    remains: int = None,
) -> Order | None:
    """Update order status + start_count/remains from API sync."""
    order = await get_order_by_id(session, order_id)
    if not order:
        return None
    order.status = status
    if start_count is not None:
        order.start_count = start_count
    if remains is not None:
        order.remains = remains
    await session.flush()
    return order


async def calc_refund(order: Order) -> float:
    """
    Calculate refund amount for cancelled/partial orders.
    - cancelled: full refund of sell_price
    - partial: refund proportional to remains
    """
    if order.status == "cancelled":
        return float(order.sell_price or 0)
    if order.status == "partial" and order.remains and order.quantity:
        rate_per_unit = float(order.sell_price) / order.quantity
        return round(rate_per_unit * order.remains, 4)
    return 0.0


async def process_refund(
    session: AsyncSession,
    order: Order,
) -> float:
    """Refund user for cancelled/partial order. Returns refunded amount."""
    from services.user_service import add_balance
    from db.models import Transaction
    refund = await calc_refund(order)
    if refund <= 0:
        return 0.0
    await add_balance(session, order.user_id, refund)
    tx = Transaction(
        user_id     = order.user_id,
        type        = "refund",
        amount      = refund,
        status      = "approved",
        method      = "auto",
        description = f"Auto refund for order #{order.id} ({order.status})",
    )
    session.add(tx)
    await session.flush()
    logger.info(f"Refunded ${refund} to user {order.user_id} for order #{order.id}")
    return refund


async def get_stale_orders(session: AsyncSession, older_than_hours: int) -> list:
    """
    سفارشاتی که بیش از older_than_hours ساعت در وضعیت pending/processing/in progress
    مانده‌اند و هنوز کنسل نشده‌اند.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import select
    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
    result = await session.execute(
        select(Order)
        .where(
            Order.status.in_(["pending", "processing", "in progress"]),
            Order.created_at <= cutoff,
        )
        .order_by(Order.created_at.asc())
    )
    return list(result.scalars().all())
