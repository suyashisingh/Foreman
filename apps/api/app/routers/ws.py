"""WebSocket endpoint for real-time run event streaming.

GET /api/v1/runs/{run_id}/ws

Authentication: first message from the client must be JSON
``{"token": "<jwt>"}``.  The server closes with code 4001 on an invalid or
missing token, or with 4003 if the run exists but belongs to a different user.

Do NOT pass the JWT as a URL query parameter — it would end up in server logs
and browser history.

Once authenticated, the server subscribes to the Redis pub/sub channel
``run:{run_id}:events`` and forwards every message to the client.  On a
terminal ``status_change`` event it sends a final ``run_complete`` message
and closes cleanly.  Client disconnects are handled without leaking the
subscription.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.db import session as _db_session
from app.db.models import Run, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

_TERMINAL_STATUSES = frozenset({"passed", "failed", "rejected", "awaiting_approval"})
_AUTH_TIMEOUT = 10.0


@router.websocket("/api/v1/runs/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: uuid.UUID) -> None:
    """Stream agent events for *run_id* over a WebSocket connection."""
    await websocket.accept()

    # ------------------------------------------------------------------
    # 1. Auth handshake — first message must carry the JWT
    # ------------------------------------------------------------------
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=_AUTH_TIMEOUT)
        msg = json.loads(raw)
        token: str = msg.get("token", "")
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception):
        await websocket.close(code=4001, reason="Auth timeout or invalid payload")
        return

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # ------------------------------------------------------------------
    # 2. Ownership check
    # ------------------------------------------------------------------
    session_factory = _db_session.async_session_factory
    if session_factory is None:
        await websocket.close(code=1011, reason="Server not ready")
        return

    async with session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            await websocket.close(code=4001, reason="Invalid token")
            return
        run = await db.get(Run, run_id)
        if run is None or run.user_id != user_id:
            await websocket.close(code=4003, reason="Run not found")
            return

    # ------------------------------------------------------------------
    # 3. Subscribe to Redis channel and stream events
    # ------------------------------------------------------------------
    redis = websocket.app.state.redis
    pubsub = redis.pubsub()
    channel = f"run:{run_id}:events"
    await pubsub.subscribe(channel)

    async def _forward() -> None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data: dict = json.loads(message["data"])
            await websocket.send_json(data)
            if data.get("type") == "status_change":
                status = data.get("data", {}).get("status", "")
                if status in _TERMINAL_STATUSES:
                    await websocket.send_json(
                        {
                            "type": "run_complete",
                            "data": {"status": status},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    return

    async def _watch_disconnect() -> None:
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    forward_task = asyncio.create_task(_forward())
    disconnect_task = asyncio.create_task(_watch_disconnect())
    try:
        await asyncio.wait(
            {forward_task, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        forward_task.cancel()
        disconnect_task.cancel()
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        for task in (forward_task, disconnect_task):
            try:
                await task
            except (asyncio.CancelledError, WebSocketDisconnect, Exception):
                pass
