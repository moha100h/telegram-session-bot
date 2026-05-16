"""
Database connection and session management.
"""
import os
import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .models import Base

logger = logging.getLogger("database")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/smmbot"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized.")

    # Insert default settings
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        defaults = [
            ("smm_markup_percent", "20",   "Markup % added to SMMPass prices for users"),
            ("min_deposit",        "1",    "Minimum deposit amount (USD)"),
            ("max_deposit",        "1000", "Maximum deposit amount (USD)"),
            ("usdt_trc20_wallet",  "",     "USDT TRC20 wallet address"),
            ("usdt_erc20_wallet",  "",     "USDT ERC20 wallet address"),
            ("ton_wallet",         "",     "TON wallet address"),
            ("trx_wallet",         "",     "TRX wallet address"),
            ("support_username",   "",     "Support Telegram username"),
            ("bot_name",           "SMM Panel", "Bot display name"),
        ]
        for key, val, desc in defaults:
            await session.execute(
                text("""
                    INSERT INTO admin_settings (key, value, description)
                    VALUES (:k, :v, :d)
                    ON CONFLICT (key) DO NOTHING
                """),
                {"k": key, "v": val, "d": desc}
            )
        await session.commit()
    logger.info("Default settings inserted.")


@asynccontextmanager
async def get_db():
    """Async context manager for DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
