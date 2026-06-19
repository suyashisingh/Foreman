"""Tests for /health and /ready endpoints.

Strategy: mocks are used for both Postgres and Redis so the suite runs
without live infrastructure.

httpx.ASGITransport sends HTTP requests directly to the ASGI app but does
NOT emit ASGI lifespan startup/shutdown events. Because of this, the
``client`` fixture injects dependencies (``app.state.redis``,
``async_session_factory``) directly rather than going through the lifespan.
This is a standard and valid approach for unit-testing the routing layer in
isolation. Integration tests that exercise the real lifespan (and real
Postgres/Redis) are added in a later task once the test-compose profile is
wired up.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.db.session as _db_session
from app.main import app


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Return a mock async session factory whose execute() succeeds.

    ``async with factory() as session`` binds ``cm.__aenter__.return_value``,
    so we wire that object up and expose it as ``factory.session`` for tests
    that need to mutate ``execute``.
    """
    cm = AsyncMock()
    # This is the object that the 'as' clause in 'async with factory() as s'
    # binds to — verified empirically (see test module docstring for why).
    session = cm.__aenter__.return_value
    session.execute = AsyncMock(return_value=None)

    factory = MagicMock(return_value=cm)
    factory.session = session  # expose so failure tests can patch execute
    return factory


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Return a mock Redis client whose ping() succeeds."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock(return_value=None)
    return client


@pytest.fixture
async def client(
    mock_db_session: MagicMock, mock_redis: AsyncMock
) -> AsyncGenerator[AsyncClient, None]:
    """Async test client with DB engine and Redis replaced by mocks.

    We bypass the lifespan by patching the session factory at module level
    and writing directly to app.state — the two side effects the lifespan
    produces that the health router depends on.
    """
    with patch.object(_db_session, "async_session_factory", mock_db_session):
        app.state.redis = mock_redis
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        # Clean up app.state so tests don't bleed into each other.
        try:
            del app.state.redis
        except AttributeError:
            pass


async def test_liveness_returns_200(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_returns_200_when_healthy(client: AsyncClient) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_readiness_returns_503_on_db_failure(
    client: AsyncClient, mock_db_session: MagicMock
) -> None:
    mock_db_session.session.execute = AsyncMock(
        side_effect=Exception("connection refused")
    )
    response = await client.get("/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert any("db" in e for e in data["errors"])


async def test_readiness_returns_503_on_redis_failure(
    client: AsyncClient, mock_redis: AsyncMock
) -> None:
    mock_redis.ping = AsyncMock(side_effect=Exception("redis timeout"))
    response = await client.get("/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert any("redis" in e for e in data["errors"])


async def test_readiness_reports_both_failures(
    client: AsyncClient, mock_db_session: MagicMock, mock_redis: AsyncMock
) -> None:
    mock_db_session.session.execute = AsyncMock(side_effect=Exception("db down"))
    mock_redis.ping = AsyncMock(side_effect=Exception("redis down"))

    response = await client.get("/ready")
    assert response.status_code == 503
    data = response.json()
    assert len(data["errors"]) == 2
