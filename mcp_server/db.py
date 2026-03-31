"""Database connection module for MCP Server.

Provides async SQLAlchemy engine and session factory.

Environment variables:
    DATABASE_URL: PostgreSQL connection string (postgresql+asyncpg://...)
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/socialhub_mcp"
)

_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def init_db() -> None:
    """Create all tables. Called at application startup."""
    from mcp_server.models import TenantBigQueryCredential  # noqa: F401 — registers model
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")


async def close_db() -> None:
    """Dispose engine. Called at application shutdown."""
    await _engine.dispose()
    logger.info("Database engine disposed")


async def get_session() -> AsyncSession:
    """Return a new async session. Caller is responsible for closing."""
    return _session_factory()
