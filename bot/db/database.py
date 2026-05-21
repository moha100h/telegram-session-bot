"""
Database connection and initialization.
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("db")

# ── ساخت DATABASE_URL از متغیرهای محیطی ──────────────────────────────────────
_host = os.getenv("POSTGRES_HOST", "postgres")
_port = os.getenv("POSTGRES_PORT", "5432")
_user = os.getenv("POSTGRES_USER", "smm")
_pass = os.getenv("POSTGRES_PASSWORD", "smm123")
_db   = os.getenv("POSTGRES_DB",   "smmbot")

# SQLAlchemy async driver — postgresql+asyncpg://
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+asyncpg://{_user}:{_pass}@{_host}:{_port}/{_db}"
)

# asyncpg مستقیم — بدون +asyncpg
ASYNCPG_DSN = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") \
                           .replace("postgres+asyncpg://",  "postgresql://")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables."""
    from db import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")
