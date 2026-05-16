"""
User service - registration, balance, verification, admin management.
"""
import os
import random
import string
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, VerificationCode, AdminUser, AdminSetting

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


async def get_or_create_user(session: AsyncSession, tg_user) -> tuple:
    """Returns (user, is_new) tuple."""
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    is_new = False
    if user is None:
        is_new = True
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            balance=0.0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        # Update username/name if changed
        changed = False
        if user.username != tg_user.username:
            user.username = tg_user.username
            changed = True
        if user.first_name != tg_user.first_name:
            user.first_name = tg_user.first_name
            changed = True
        if changed:
            await session.commit()
    return user, is_new


async def get_user(session: AsyncSession, telegram_id: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int):
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def set_phone(session: AsyncSession, telegram_id: int, phone: str):
    await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id)
        .values(phone=phone, updated_at=datetime.utcnow())
    )
    await session.commit()


async def add_balance(session: AsyncSession, user_id: int, amount: float):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.balance = float(user.balance or 0) + amount
        user.updated_at = datetime.utcnow()
        await session.commit()


async def deduct_balance(session: AsyncSession, user_id: int, amount: float) -> bool:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and float(user.balance or 0) >= amount:
        user.balance = float(user.balance) - amount
        user.updated_at = datetime.utcnow()
        await session.commit()
        return True
    return False


async def ban_user(session: AsyncSession, telegram_id: int):
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(is_banned=True)
    )
    await session.commit()


async def unban_user(session: AsyncSession, telegram_id: int):
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(is_banned=False)
    )
    await session.commit()


async def get_all_users(session: AsyncSession) -> list:
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row and row.value is not None else default


async def set_setting(session: AsyncSession, key: str, value: str):
    result = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(AdminSetting(key=key, value=value))
    await session.commit()


async def get_admin(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(AdminUser).where(AdminUser.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    return (await get_admin(session, telegram_id)) is not None


async def get_all_admins(session: AsyncSession) -> list:
    result = await session.execute(select(AdminUser).order_by(AdminUser.created_at.desc()))
    return result.scalars().all()


async def add_admin(session: AsyncSession, telegram_id: int, username: str = None, role: str = "admin") -> AdminUser:
    existing = await get_admin(session, telegram_id)
    if existing:
        existing.role = role
        if username:
            existing.username = username
        await session.commit()
        return existing
    admin = AdminUser(
        telegram_id=telegram_id,
        username=username,
        role=role,
        permissions="{}",
    )
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


async def remove_admin(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(
        select(AdminUser).where(AdminUser.telegram_id == telegram_id)
    )
    admin = result.scalar_one_or_none()
    if admin:
        await session.delete(admin)
        await session.commit()
        return True
    return False


async def create_verification_code(session: AsyncSession, telegram_id: int) -> str:
    code = "".join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    session.add(VerificationCode(
        telegram_id=telegram_id,
        code=code,
        expires_at=expires_at,
        is_used=False,
    ))
    await session.commit()
    return code


async def verify_code(session: AsyncSession, telegram_id: int, code: str) -> bool:
    result = await session.execute(
        select(VerificationCode).where(
            VerificationCode.telegram_id == telegram_id,
            VerificationCode.code == code,
            VerificationCode.is_used == False,
            VerificationCode.expires_at > datetime.utcnow(),
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.is_used = True
        await session.commit()
        return True
    return False
