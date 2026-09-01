"""Async database session construction."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from jb_orchestrator.config import Settings, get_settings


def create_session_factory(
    settings: Settings | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory for the configured database."""

    resolved = settings or get_settings()
    engine = create_async_engine(resolved.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)
