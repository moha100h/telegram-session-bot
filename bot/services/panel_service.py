"""
Panel service — CRUD for Panel, PanelCategory, PanelService, PanelOrder.
"""
from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from db.models import Panel, PanelCategory, PanelService, PanelOrder, User, Transaction

logger = logging.getLogger("panel_service")


# ── Panel CRUD ────────────────────────────────────────────────────────────────

async def get_all_panels(session: AsyncSession, active_only: bool = False) -> list[Panel]:
    q = select(Panel).order_by(Panel.order_index, Panel.id)
    if active_only:
        q = q.where(Panel.is_active == True)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_panel(session: AsyncSession, panel_id: int) -> Optional[Panel]:
    res = await session.execute(
        select(Panel).where(Panel.id == panel_id)
        .options(selectinload(Panel.categories).selectinload(PanelCategory.services))
    )
    return res.scalar_one_or_none()


async def create_panel(session: AsyncSession, name: str, button_label: str,
                       description: str = "", group_chat_id: int = None) -> Panel:
    panel = Panel(name=name, button_label=button_label,
                  description=description, group_chat_id=group_chat_id)
    session.add(panel)
    await session.flush()
    return panel


async def update_panel(session: AsyncSession, panel_id: int, **kwargs) -> bool:
    res = await session.execute(
        update(Panel).where(Panel.id == panel_id).values(**kwargs)
    )
    return res.rowcount > 0


async def delete_panel(session: AsyncSession, panel_id: int) -> bool:
    res = await session.execute(select(Panel).where(Panel.id == panel_id))
    panel = res.scalar_one_or_none()
    if not panel: return False
    await session.delete(panel)
    return True


# ── Category CRUD ─────────────────────────────────────────────────────────────

async def get_categories(session: AsyncSession, panel_id: int,
                         active_only: bool = False) -> list[PanelCategory]:
    q = select(PanelCategory).where(PanelCategory.panel_id == panel_id)        .order_by(PanelCategory.order_index, PanelCategory.id)
    if active_only:
        q = q.where(PanelCategory.is_active == True)
    res = await session.execute(q)
    return list(res.scalars().all())


async def create_category(session: AsyncSession, panel_id: int,
                          name: str, icon: str = "📂") -> PanelCategory:
    cat = PanelCategory(panel_id=panel_id, name=name, icon=icon)
    session.add(cat)
    await session.flush()
    return cat


async def update_category(session: AsyncSession, cat_id: int, **kwargs) -> bool:
    res = await session.execute(
        update(PanelCategory).where(PanelCategory.id == cat_id).values(**kwargs)
    )
    return res.rowcount > 0


async def delete_category(session: AsyncSession, cat_id: int) -> bool:
    res = await session.execute(select(PanelCategory).where(PanelCategory.id == cat_id))
    cat = res.scalar_one_or_none()
    if not cat: return False
    await session.delete(cat)
    return True


# ── Service CRUD ──────────────────────────────────────────────────────────────

async def get_services(session: AsyncSession, category_id: int,
                       active_only: bool = False) -> list[PanelService]:
    q = select(PanelService).where(PanelService.category_id == category_id)        .order_by(PanelService.order_index, PanelService.id)
    if active_only:
        q = q.where(PanelService.is_active == True)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_service(session: AsyncSession, service_id: int) -> Optional[PanelService]:
    res = await session.execute(select(PanelService).where(PanelService.id == service_id))
    return res.scalar_one_or_none()


async def create_service(session: AsyncSession, category_id: int, name: str,
                         price: float, min_qty: int, max_qty: int,
                         description: str = "") -> PanelService:
    svc = PanelService(category_id=category_id, name=name, price=price,
                       min_qty=min_qty, max_qty=max_qty, description=description)
    session.add(svc)
    await session.flush()
    return svc


async def update_service(session: AsyncSession, svc_id: int, **kwargs) -> bool:
    res = await session.execute(
        update(PanelService).where(PanelService.id == svc_id).values(**kwargs)
    )
    return res.rowcount > 0


async def delete_service(session: AsyncSession, svc_id: int) -> bool:
    res = await session.execute(select(PanelService).where(PanelService.id == svc_id))
    svc = res.scalar_one_or_none()
    if not svc: return False
    await session.delete(svc)
    return True


# ── PanelOrder ────────────────────────────────────────────────────────────────

async def create_panel_order(session: AsyncSession, user_id: int, panel_id: int,
                             service_id: int, service_name: str, panel_name: str,
                             quantity: int, unit_price: float, total_price: float,
                             link: str = "", note: str = "") -> PanelOrder:
    order = PanelOrder(
        user_id=user_id, panel_id=panel_id, service_id=service_id,
        service_name=service_name, panel_name=panel_name,
        quantity=quantity, unit_price=unit_price, total_price=total_price,
        link=link, note=note, status="pending",
    )
    session.add(order)
    await session.flush()
    return order


async def get_panel_order(session: AsyncSession, order_id: int) -> Optional[PanelOrder]:
    res = await session.execute(
        select(PanelOrder).where(PanelOrder.id == order_id)
        .options(selectinload(PanelOrder.user))
    )
    return res.scalar_one_or_none()


async def get_user_panel_orders(session: AsyncSession, user_id: int,
                                limit: int = 20, offset: int = 0) -> list[PanelOrder]:
    res = await session.execute(
        select(PanelOrder).where(PanelOrder.user_id == user_id)
        .order_by(PanelOrder.created_at.desc())
        .limit(limit).offset(offset)
    )
    return list(res.scalars().all())


async def update_panel_order_status(session: AsyncSession, order_id: int,
                                    status: str, completed_qty: int = None,
                                    admin_note: str = None) -> Optional[PanelOrder]:
    order = await get_panel_order(session, order_id)
    if not order: return None
    order.status = status
    if completed_qty is not None:
        order.completed_qty = completed_qty
    if admin_note:
        order.admin_note = admin_note
    return order


async def process_panel_refund(session: AsyncSession, order: PanelOrder,
                               completed_qty: int = 0) -> float:
    """محاسبه و برگشت مبلغ — کامل یا جزئی"""
    if completed_qty == 0:
        refund = order.total_price
    else:
        done_ratio = completed_qty / max(order.quantity, 1)
        refund = round(order.total_price * (1 - done_ratio), 6)

    if refund > 0:
        user_res = await session.execute(select(User).where(User.id == order.user_id))
        user = user_res.scalar_one_or_none()
        if user:
            user.balance = round((user.balance or 0) + refund, 6)
            txn = Transaction(
                user_id=order.user_id,
                type="refund",
                amount=refund,
                status="completed",
                method="panel",
                description=f"بازگشت وجه سفارش #{order.id}",
            )
            session.add(txn)
    order.refund_amount = refund
    return refund
