"""
User service - registration, balance, verification.
"""
import os
import random
import string
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, VerificationCode, AdminUser, AdminSetting

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    if not user:
        ref = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            referral_code=ref,
        )
        session.add(user)
        await session.flush()
    else:
        user.username   = tg_user.username
        user.first_name = tg_user.first_name
        user.last_name  = tg_user.last_name
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    r = await session.execute(select(User).where(User.id == user_id))
    return r.scalar_one_or_none()


async def add_balance(session: AsyncSession, user_id: int, amount: float):
    await session.execute(
        update(User).where(User.id == user_id)
        .values(balance=User.balance + amount)
    )


async def deduct_balance(session: AsyncSession, user_id: int, amount: float) -> bool:
    r = await session.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if not user or float(user.balance) < amount:
        return False
    await session.execute(
        update(User).where(User.id == user_id)
        .values(balance=User.balance - amount)
    )
    return True


async def ban_user(session: AsyncSession, telegram_id: int):
    await session.execute(update(User).where(User.telegram_id == telegram_id).values(is_banned=True))


async def unban_user(session: AsyncSession, telegram_id: int):
    await session.execute(update(User).where(User.telegram_id == telegram_id).values(is_banned=False))


async def get_all_users(session: AsyncSession) -> list[User]:
    r = await session.execute(select(User).order_by(User.created_at.desc()))
    return r.scalars().all()


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    r = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    s = r.scalar_one_or_none()
    return s.value if s else default


async def set_setting(session: AsyncSession, key: str, value: str):
    r = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    s = r.scalar_one_or_none()
    if s:
        s.value = value
        s.updated_at = datetime.utcnow()
    else:
        session.add(AdminSetting(key=key, value=value))


async def get_admin(session: AsyncSession, telegram_id: int) -> AdminUser | None:
    r = await session.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id))
    return r.scalar_one_or_none()


async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    if telegram_id == ADMIN_ID:
        return True
    admin = await get_admin(session, telegram_id)
    return admin is not None


async def create_verification_code(session: AsyncSession, telegram_id: int) -> str:
    code = "".join(random.choices(string.digits, k=6))
    expires = datetime.utcnow() + timedelta(minutes=5)
    session.add(VerificationCode(telegram_id=telegram_id, code=code, expires_at=expires))
    return code


async def verify_code(session: AsyncSession, telegram_id: int, code: str) -> bool:
    r = await session.execute(
        select(VerificationCode).where(
            VerificationCode.telegram_id == telegram_id,
            VerificationCode.code == code,
            VerificationCode.is_used == False,
            VerificationCode.expires_at > datetime.utcnow()
        )
    )
    vc = r.scalar_one_or_none()
    if vc:
        vc.is_used = True
        return True
    return False
