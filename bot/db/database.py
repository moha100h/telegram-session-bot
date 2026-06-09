"""
Database connection and initialization.
"""
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("db")

# اگه DATABASE_URL مستقیم ست بود استفاده کن، وگرنه از اجزا بساز
_db_url = os.getenv("DATABASE_URL")
if not _db_url:
    _host = os.getenv("POSTGRES_HOST", "postgres")
    _port = os.getenv("POSTGRES_PORT", "5432")
    _user = os.getenv("POSTGRES_USER", "smm")
    _pass = os.getenv("POSTGRES_PASSWORD", "")
    _db   = os.getenv("POSTGRES_DB", "smmbot")
    _db_url = f"postgresql+asyncpg://{_user}:{_pass}@{_host}:{_port}/{_db}"

DATABASE_URL = _db_url

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
    from db import models  # noqa: F401 - import to register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")
