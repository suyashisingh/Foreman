"""WebSocket endpoint auth-handshake tests.

Uses FastAPI's synchronous TestClient (starlette.testclient.TestClient) for
WebSocket connections.  Data is seeded via asyncio.run() into the same test
database that the app's lifespan connects to when the TestClient starts.
"""

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.db.models import Repo, RepoStatus, Run, RunStatus, User
from app.main import create_app

# Conftest injects DATABASE_URL before any app import; fall back to local dev port.
_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://foreman:foreman_secret@localhost:5434/foreman_test",
)


def _seed_ws_data() -> tuple[str, str, uuid.UUID]:
    """Insert a user, repo, and run; return (token_owner, token_other, run_id).

    Runs synchronously via asyncio.run() so it can be called from a plain
    (non-async) pytest fixture or test.
    """

    async def _async() -> tuple[str, str, uuid.UUID]:
        engine = create_async_engine(_DB_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with Session() as db:
                suffix = uuid.uuid4().hex[:8]
                owner = User(
                    email=f"wsown_{suffix}@test.com",
                    password_hash="argon2id$notreal",
                    name="Owner",
                )
                other = User(
                    email=f"wsoth_{suffix}@test.com",
                    password_hash="argon2id$notreal",
                    name="Other",
                )
                db.add_all([owner, other])
                await db.flush()

                repo = Repo(
                    user_id=owner.id,
                    name="ws-repo",
                    clone_url="https://github.com/test/repo.git",
                    default_branch="main",
                    status=RepoStatus.ready,
                )
                db.add(repo)
                await db.flush()

                run = Run(
                    user_id=owner.id,
                    repo_id=repo.id,
                    issue_text="WS integration test",
                    status=RunStatus.pending,
                )
                db.add(run)
                await db.commit()

                return (
                    create_access_token(str(owner.id)),
                    create_access_token(str(other.id)),
                    run.id,
                )
        finally:
            await engine.dispose()

    return asyncio.run(_async())


# ---------------------------------------------------------------------------
# Tests — auth rejection (no DB seed needed for these)
# ---------------------------------------------------------------------------


def test_ws_rejects_invalid_token():
    run_id = uuid.uuid4()
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with TestClient(create_app()) as client:
            with client.websocket_connect(f"/api/v1/runs/{run_id}/ws") as ws:
                ws.send_json({"token": "not-a-valid-jwt"})
                ws.receive_json()
    assert exc_info.value.code == 4001


def test_ws_rejects_missing_token():
    run_id = uuid.uuid4()
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with TestClient(create_app()) as client:
            with client.websocket_connect(f"/api/v1/runs/{run_id}/ws") as ws:
                ws.send_json({})  # no "token" key
                ws.receive_json()
    assert exc_info.value.code == 4001


# ---------------------------------------------------------------------------
# Tests — ownership check (DB seed required)
# ---------------------------------------------------------------------------


def test_ws_rejects_wrong_user_run():
    token_owner, token_other, run_id = _seed_ws_data()
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with TestClient(create_app()) as client:
            with client.websocket_connect(f"/api/v1/runs/{run_id}/ws") as ws:
                ws.send_json({"token": token_other})
                ws.receive_json()
    assert exc_info.value.code == 4003


def test_ws_accepts_valid_token_and_owned_run():
    token_owner, _other, run_id = _seed_ws_data()
    # If auth fails the server closes immediately and the with block raises
    # WebSocketDisconnect.  No exception here means auth succeeded.
    with TestClient(create_app()) as client:
        with client.websocket_connect(f"/api/v1/runs/{run_id}/ws") as ws:
            ws.send_json({"token": token_owner})
            # Connection is alive; close cleanly from client side.
