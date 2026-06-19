"""Shared test fixtures.

JWT_SECRET_KEY and VOYAGE_API_KEY are injected into os.environ BEFORE any
app module is imported so that pydantic-settings doesn't raise a
ValidationError at collection time.
"""

import os

# Must happen before any app import.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production!!")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://foreman:foreman_secret@localhost:5434/foreman_test",
)
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key-not-real")

import textwrap
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
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


# ---------------------------------------------------------------------------
# DB access fixtures (for task-level and search tests that bypass HTTP)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """An AsyncSession for direct DB manipulation in tests."""
    async with _TestSession() as session:
        yield session


@pytest.fixture
def session_factory():
    """The test async_sessionmaker — pass as ctx['session_factory'] to tasks."""
    return _TestSession


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_arq_pool():
    """A mock ARQ pool that records enqueue_job calls without hitting Redis."""
    return AsyncMock()


@pytest_asyncio.fixture
async def client(mock_arq_pool):
    """AsyncClient wired to the FastAPI app with test overrides injected."""
    app = create_app()

    async def _override_get_db():
        async with _TestSession() as session:
            yield session

    app.dependency_overrides[_deps.get_db] = _override_get_db
    app.dependency_overrides[_deps.get_arq_pool] = lambda: mock_arq_pool

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


_AUTH_USER = {
    "email": "testuser@example.com",
    "password": "testpassword1",
    "name": "Test",
}


@pytest_asyncio.fixture
async def auth_client(client):
    """AsyncClient pre-loaded with a valid Bearer token."""
    reg = await client.post("/api/v1/auth/register", json=_AUTH_USER)
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ---------------------------------------------------------------------------
# Shared test data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo_dir(tmp_path: Path) -> Path:
    """A tiny fake cloned repo with two Python source files."""
    (tmp_path / "calculator.py").write_text(
        textwrap.dedent("""\
            class Calculator:
                \"\"\"A simple calculator.\"\"\"

                def add(self, a: int, b: int) -> int:
                    return a + b

                def subtract(self, a: int, b: int) -> int:
                    return a - b

            def greet(name: str) -> str:
                return f"Hello, {name}!"
        """)
    )
    (tmp_path / "utils.py").write_text(
        textwrap.dedent("""\
            import os

            def get_env(key: str, default: str = "") -> str:
                return os.environ.get(key, default)
        """)
    )
    return tmp_path
