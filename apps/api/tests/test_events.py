"""Tests for the Redis pub/sub event publishing helpers."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.orchestrator import events


@pytest.fixture(autouse=True)
def _restore_redis():
    """Restore the module-level _redis client after each test."""
    original = events._redis
    yield
    events._redis = original


def test_set_redis_client_stores_client():
    mock = MagicMock()
    events.set_redis_client(mock)
    assert events._redis is mock


@pytest.mark.asyncio
async def test_publish_run_event_sends_to_correct_channel():
    mock_redis = AsyncMock()
    events.set_redis_client(mock_redis)

    run_id = uuid.uuid4()
    await events.publish_run_event(run_id, "agent_step", {"agent": "planner"})

    mock_redis.publish.assert_awaited_once()
    channel, payload_str = mock_redis.publish.call_args[0]
    assert channel == f"run:{run_id}:events"
    payload = json.loads(payload_str)
    assert payload["type"] == "agent_step"
    assert payload["data"]["agent"] == "planner"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_publish_run_event_noop_without_client():
    events.set_redis_client(None)
    run_id = uuid.uuid4()
    # Must not raise
    await events.publish_run_event(run_id, "agent_step", {})


@pytest.mark.asyncio
async def test_publish_run_event_swallows_redis_errors():
    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = Exception("Redis connection refused")
    events.set_redis_client(mock_redis)

    run_id = uuid.uuid4()
    # Must not raise
    await events.publish_run_event(run_id, "status_change", {"status": "failed"})


@pytest.mark.asyncio
async def test_publish_run_event_status_change_shape():
    mock_redis = AsyncMock()
    events.set_redis_client(mock_redis)

    run_id = uuid.uuid4()
    await events.publish_run_event(
        run_id, "status_change", {"status": "awaiting_approval"}
    )

    _, payload_str = mock_redis.publish.call_args[0]
    payload = json.loads(payload_str)
    assert payload["type"] == "status_change"
    assert payload["data"]["status"] == "awaiting_approval"
