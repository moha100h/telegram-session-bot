"""
Order service - create orders with markup, track status.
"""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Order, Transaction, AdminSetting
from services.user_service import deduct_balance


async def get_markup(session: AsyncSession) -> float:
    """Get SMM markup percentage from settings."""
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.key == "smm_markup_percent")
    )
    setting = result.scalar_one_or_none()
    try:
        return float(setting.value) if setting else 20.0
    except Exception:
        return 20.0


def apply_markup(base_price: float, markup_pct: float) -> float:
    """Apply markup percentage to base price."""
    return round(base_price * (1 + markup_pct / 100), 4)


async def calc_order_price(session: AsyncSession, rate_per_1000: float, quantity: int) -> dict:
    """Calculate cost and sell price for an order."""
    markup = await get_markup(session)
    cost   = round(rate_per_1000 * quantity / 1000, 4)
    sell   = apply_markup(cost, markup)
    return {"cost": cost, "sell": sell, "markup_pct": markup}


async def create_order(
    session: AsyncSession,
    user_id: int,
    service_id: int,
    service_name: str,
    link: str,
    quantity: int,
    cost_price: float,
    sell_price: float,
) -> Order | None:
    """Deduct balance and create order record."""
    ok = await deduct_balance(session, user_id, sell_price)
    if not ok:
        return None

    order = Order(
        user_id      = user_id,
        service_id   = service_id,
        service_name = service_name,
        link         = link,
        quantity     = quantity,
        cost_price   = cost_price,
        sell_price   = sell_price,
        status       = "pending",
    )
    session.add(order)

    # Record transaction
    tx = Transaction(
        user_id     = user_id,
        type        = "order",
        amount      = -sell_price,
        status      = "approved",
        description = f"Order #{service_id} - {service_name[:50]}",
    )
    session.add(tx)
    await session.flush()
    return order


async def get_user_orders(session: AsyncSession, user_id: int,
                          page: int = 0, page_size: int = 10) -> list[Order]:
    result = await session.execute(
        select(Order).where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .offset(page * page_size).limit(page_size)
    )
    return list(result.scalars().all())


async def get_all_orders(session: AsyncSession, page: int = 0, page_size: int = 20) -> list[Order]:
    result = await session.execute(
        select(Order).order_by(Order.created_at.desc())
        .offset(page * page_size).limit(page_size)
    )
    return list(result.scalars().all())


async def update_order_status(session: AsyncSession, order_id: int,
                               status: str, start_count: int = None,
                               remains: int = None) -> bool:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        return False
    order.status = status
    if start_count is not None:
        order.start_count = start_count
    if remains is not None:
        order.remains = remains
    return True
