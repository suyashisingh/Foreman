"""Tests for /api/v1/system/status and /api/v1/repos/{id}/cost-estimate endpoints."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.models import Repo, RepoStatus, User

SYSTEM_URL = "/api/v1/system/status"
REPOS_URL = "/api/v1/repos"
_AUTH_USER = {
    "email": "systest@example.com",
    "password": "testpassword123",
    "name": "Sys",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_client(client):
    reg = await client.post("/api/v1/auth/register", json=_AUTH_USER)
    assert reg.status_code == 201, reg.text
    client.headers.update({"Authorization": f"Bearer {reg.json()['access_token']}"})
    return client


@pytest_asyncio.fixture
async def ready_repo(db, auth_client):
    result = await db.execute(select(User).where(User.email == _AUTH_USER["email"]))
    user = result.scalar_one()
    repo = Repo(
        user_id=user.id,
        name="sys-test-repo",
        clone_url="https://github.com/example/sys-repo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return repo


# ---------------------------------------------------------------------------
# GET /api/v1/system/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_status_is_public(client):
    """GET /system/status requires no authentication."""
    resp = await client.get(SYSTEM_URL)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_system_status_response_shape(client):
    """GET /system/status returns the expected fields."""
    resp = await client.get(SYSTEM_URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "database_ok" in body
    assert "redis_ok" in body
    assert "gemini_key_configured" in body
    assert "voyage_key_configured" in body
    assert "e2b_key_configured" in body
    assert "gemini_model" in body
    assert isinstance(body["database_ok"], bool)
    assert isinstance(body["gemini_key_configured"], bool)


@pytest.mark.asyncio
async def test_system_status_keys_configured(client):
    """API keys present in the test environment are reported as configured."""
    resp = await client.get(SYSTEM_URL)
    body = resp.json()
    # conftest sets test values for all three keys — they should be "configured"
    assert body["gemini_key_configured"] is True
    assert body["voyage_key_configured"] is True
    assert body["e2b_key_configured"] is True


@pytest.mark.asyncio
async def test_system_status_never_exposes_key_values(client):
    """The response must not contain actual key values."""
    resp = await client.get(SYSTEM_URL)
    text = resp.text
    # None of the test key strings should appear in the response
    assert "test-gemini-key" not in text
    assert "test-voyage-key" not in text
    assert "test-e2b-key" not in text


@pytest.mark.asyncio
async def test_system_status_model_name_present(client):
    """gemini_model is a non-empty string."""
    resp = await client.get(SYSTEM_URL)
    body = resp.json()
    assert isinstance(body["gemini_model"], str)
    assert len(body["gemini_model"]) > 0


# ---------------------------------------------------------------------------
# GET /api/v1/repos/{id}/cost-estimate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_estimate_requires_auth(client):
    """GET /repos/{id}/cost-estimate without a token returns 401."""
    resp = await client.get(f"{REPOS_URL}/{uuid.uuid4()}/cost-estimate")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_cost_estimate_returns_estimate(auth_client, ready_repo):
    """GET /repos/{id}/cost-estimate returns estimated_usd and chunk_count."""
    resp = await auth_client.get(f"{REPOS_URL}/{ready_repo.id}/cost-estimate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "estimated_usd" in body
    assert "chunk_count" in body
    assert isinstance(body["estimated_usd"], float)
    assert body["estimated_usd"] > 0
    assert body["chunk_count"] == 0  # no chunks seeded in this fixture


@pytest.mark.asyncio
async def test_cost_estimate_returns_404_for_other_user(auth_client, db):
    """GET /repos/{id}/cost-estimate returns 404 for another user's repo."""
    other = User(
        email="other_cost@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Other",
    )
    db.add(other)
    await db.flush()
    other_repo = Repo(
        user_id=other.id,
        name="other-repo",
        clone_url="https://github.com/x/y.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(other_repo)
    await db.commit()

    resp = await auth_client.get(f"{REPOS_URL}/{other_repo.id}/cost-estimate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cost_estimate_404_unknown_repo(auth_client):
    """GET /repos/{unknown_id}/cost-estimate returns 404."""
    resp = await auth_client.get(f"{REPOS_URL}/{uuid.uuid4()}/cost-estimate")
    assert resp.status_code == 404
