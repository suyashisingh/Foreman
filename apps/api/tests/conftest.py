"""Shared test fixtures.

JWT_SECRET_KEY is injected into os.environ BEFORE any app module is imported so
that pydantic-settings doesn't raise a ValidationError at collection time.
"""

import os

# Must happen before any app import.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production!!")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://foreman:foreman_secret@localhost:5434/foreman_test",
)
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key-not-real")

import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import deps as _deps
from app.db import models as _models  # noqa: F401 — registers ORM classes
from app.db.base import Base
from app.main import create_app

TEST_DB_URL = os.environ["DATABASE_URL"]

_engine = create_async_engine(TEST_DB_URL, echo=False)
_TestSession = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """Create all tables once per test session; drop them afterwards."""
    async with _engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


_APP_TABLE_NAMES = ",".join(
    f'"{t.name}"' for t in Base.metadata.sorted_tables if t.name != "alembic_version"
)


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables():
    """Truncate all app tables between tests — atomic and FK-safe."""
    yield
    async with _engine.begin() as conn:
        await conn.execute(
            sa.text(f"TRUNCATE TABLE {_APP_TABLE_NAMES} RESTART IDENTITY CASCADE")
        )


@pytest_asyncio.fixture
async def client():
    """AsyncClient wired to the FastAPI app with the test DB session injected."""
    app = create_app()

    async def _override_get_db():
        async with _TestSession() as session:
            yield session

    app.dependency_overrides[_deps.get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
