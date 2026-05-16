"""
User service - registration, verification, balance management.
"""
import random
import string
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import User, VerificationCode, AdminUser


def _gen_referral() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


async def get_or_create_user(session: AsyncSession, tg_user) -> tuple[User, bool]:
    """Get existing user or create new one. Returns (user, is_new)."""
    result = await session.execute(
        select(User).where(User.telegram_id == tg_user.id)
    )
    user = result.scalar_one_or_none()
    if user:
        # Update name/username
        user.username   = tg_user.username
        user.first_name = tg_user.first_name
        user.last_name  = tg_user.last_name
        user.updated_at = datetime.utcnow()
        return user, False

    # Create new user
    ref = _gen_referral()
    user = User(
        telegram_id   = tg_user.id,
        username      = tg_user.username,
        first_name    = tg_user.first_name,
        last_name     = tg_user.last_name,
        referral_code = ref,
        balance       = 0,
    )
    session.add(user)
    await session.flush()
    return user, True


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_all_users(session: AsyncSession, page: int = 0, page_size: int = 20) -> list[User]:
    result = await session.execute(
        select(User).order_by(User.created_at.desc())
        .offset(page * page_size).limit(page_size)
    )
    return list(result.scalars().all())


async def count_users(session: AsyncSession) -> int:
    from sqlalchemy import func
    result = await session.execute(select(func.count(User.id)))
    return result.scalar_one()


async def ban_user(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(
        update(User).where(User.telegram_id == telegram_id)
        .values(is_banned=True)
    )
    return result.rowcount > 0


async def unban_user(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(
        update(User).where(User.telegram_id == telegram_id)
        .values(is_banned=False)
    )
    return result.rowcount > 0


async def add_balance(session: AsyncSession, user_id: int, amount: float) -> User | None:
    user = await get_user_by_id(session, user_id)
    if user:
        user.balance = float(user.balance or 0) + amount
        user.updated_at = datetime.utcnow()
    return user


async def deduct_balance(session: AsyncSession, user_id: int, amount: float) -> bool:
    user = await get_user_by_id(session, user_id)
    if not user:
        return False
    if float(user.balance or 0) < amount:
        return False
    user.balance = float(user.balance) - amount
    user.updated_at = datetime.utcnow()
    return True


async def set_phone(session: AsyncSession, telegram_id: int, phone: str) -> bool:
    result = await session.execute(
        update(User).where(User.telegram_id == telegram_id)
        .values(phone=phone)
    )
    return result.rowcount > 0


# --- Verification codes ---

async def create_verification_code(session: AsyncSession, telegram_id: int) -> str:
    code = "".join(random.choices(string.digits, k=6))
    expires = datetime.utcnow() + timedelta(minutes=5)
    vc = VerificationCode(
        telegram_id=telegram_id,
        code=code,
        expires_at=expires,
    )
    session.add(vc)
    await session.flush()
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
    vc = result.scalar_one_or_none()
    if not vc:
        return False
    vc.is_used = True
    return True


# --- Admin users ---

async def get_admin(session: AsyncSession, telegram_id: int) -> AdminUser | None:
    result = await session.execute(
        select(AdminUser).where(AdminUser.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_all_admins(session: AsyncSession) -> list[AdminUser]:
    result = await session.execute(select(AdminUser).order_by(AdminUser.created_at))
    return list(result.scalars().all())


async def add_admin(session: AsyncSession, telegram_id: int, username: str,
                   role: str = "admin", permissions: dict = None) -> AdminUser:
    import json
    perms = json.dumps(permissions or {
        "manage_users": True,
        "manage_orders": True,
        "manage_deposits": True,
        "view_stats": True,
        "manage_settings": False,
    })
    admin = AdminUser(
        telegram_id=telegram_id,
        username=username,
        role=role,
        permissions=perms,
    )
    session.add(admin)
    await session.flush()
    return admin


async def remove_admin(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(
        select(AdminUser).where(AdminUser.telegram_id == telegram_id)
    )
    admin = result.scalar_one_or_none()
    if admin:
        await session.delete(admin)
        return True
    return False


async def update_admin_permissions(session: AsyncSession, telegram_id: int, permissions: dict) -> bool:
    import json
    result = await session.execute(
        update(AdminUser).where(AdminUser.telegram_id == telegram_id)
        .values(permissions=json.dumps(permissions))
    )
    return result.rowcount > 0
