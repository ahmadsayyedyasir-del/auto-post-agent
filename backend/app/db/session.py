"""SQLAlchemy 2.x async engine, session factory, and database dependency providers."""

from collections.abc import AsyncGenerator
import logging
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_async_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return a cached or newly initialized asynchronous SQLAlchemy engine."""
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        url = cfg.database_url

        engine_kwargs: dict[str, Any] = {
            "echo": cfg.database_echo,
            "future": True,
        }

        # Dialect-specific connection arguments
        if url.startswith("sqlite"):
            # SQLite does not support standard server connection pooling parameters
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # PostgreSQL connection pool settings
            engine_kwargs["pool_size"] = cfg.database_pool_size
            engine_kwargs["max_overflow"] = cfg.database_max_overflow
            engine_kwargs["pool_recycle"] = cfg.database_pool_recycle

        logger.info("Initializing SQLAlchemy async engine with dialect: %s", url.split(":")[0])
        _engine = create_async_engine(url, **engine_kwargs)

    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Return an async session maker instance."""
    global _session_factory
    if _session_factory is None:
        engine = get_async_engine(settings)
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session within a transaction context."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db_engine() -> None:
    """Dispose of the global database engine (useful on application shutdown or test teardown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("SQLAlchemy async engine disposed.")
