import logging
import time
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ORM Base
class Base(DeclarativeBase):
    pass

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

def init_db() -> None:
    global _engine
    global _session_factory

    settings = get_settings()

    engine_kwargs = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": False,
    }

    _engine = create_async_engine(
        settings.database_url,
        **engine_kwargs,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    logger.info("Database engines initialized.")

async def close_db() -> None:
    if _engine:
        await _engine.dispose()
        logger.info("DB engine disposed")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() at startup.")
    
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.error("Database session error, rolled back: %s", exc, exc_info=True)
        except Exception:
            await session.rollback()
            raise

async def ping_database() -> dict:
    if _engine is None:
        raise RuntimeError("Database not initialised. Call init_db() at startup.")
    
    start = time.monotonic()
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": "ok",
            "latency_ms": latency_ms
        }
    except OperationalError as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        logger.error("Database health check failed: %s", exc)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "detail": str(exc)
        }