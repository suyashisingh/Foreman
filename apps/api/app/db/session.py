"""Async SQLAlchemy engine and session factory.

No ORM models are defined here — that is a separate task. This module owns
engine lifecycle (create on startup, dispose on shutdown) and exposes an
``async_session_factory`` for use in route dependencies and the readiness
check.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Module-level singletons; populated by init_engine() inside the lifespan.
engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> None:
    """Create the async engine and session factory.

    Called once during application startup. Uses ``pool_pre_ping`` so
    stale connections are detected and replaced transparently.
    """
    global engine, async_session_factory

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.ENVIRONMENT == "development",
        pool_pre_ping=True,
    )
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def close_engine() -> None:
    """Dispose the engine connection pool on application shutdown."""
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None
