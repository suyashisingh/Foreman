"""Integration tests for /api/v1/auth/* — run against a real Postgres DB."""

import time

import jwt as pyjwt
import pytest

from app.core.config import settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"

VALID_USER = {
    "email": "alice@example.com",
    "password": "testpassword123",
    "name": "Alice",
}


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_returns_201_and_token(client):
    resp = await client.post(REGISTER_URL, json=VALID_USER)
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    resp = await client.post(REGISTER_URL, json=VALID_USER)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client):
    resp = await client.post(
        REGISTER_URL,
        json={"email": "bob@example.com", "password": "short"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_happy_path_returns_token(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client):
    await client.post(REGISTER_URL, json=VALID_USER)
    resp = await client.post(
        LOGIN_URL,
        json={"email": VALID_USER["email"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials."


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client):
    resp = await client.post(
        LOGIN_URL,
        json={"email": "nobody@example.com", "password": "irrelevant"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials."


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_with_valid_token_returns_user(client):
    reg = await client.post(REGISTER_URL, json=VALID_USER)
    token = reg.json()["access_token"]
    resp = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == VALID_USER["email"]
    assert body["name"] == VALID_USER["name"]
    assert "password_hash" not in body
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client):
    resp = await client.get(ME_URL)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_with_expired_token_returns_401(client):
    reg = await client.post(REGISTER_URL, json=VALID_USER)
    token = reg.json()["access_token"]

    # Decode, backdate exp, re-sign with the same secret.
    payload = pyjwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    payload["exp"] = int(time.time()) - 1  # already expired
    expired_token = pyjwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )

    resp = await client.get(
        ME_URL, headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_tampered_token_returns_401(client):
    resp = await client.get(
        ME_URL, headers={"Authorization": "Bearer this.is.not.a.valid.jwt"}
    )
    assert resp.status_code == 401
