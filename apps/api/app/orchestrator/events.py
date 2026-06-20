"""Redis pub/sub helpers for broadcasting run events.

Publishes JSON messages to ``run:{run_id}:events`` channels so WebSocket
subscribers in the API process can forward real-time updates to clients.

The module-level ``_redis`` client is set once by the ARQ worker's startup
hook (``WorkerSettings.on_startup``).  In the API process it remains ``None``
so calls from there are silently no-ops — events only flow from the worker.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_redis: Any | None = None


def set_redis_client(client: Any) -> None:
    """Register the module-level Redis client for event publishing.

    Called once from the worker's on_startup hook.
    """
    global _redis
    _redis = client


async def publish_run_event(
    run_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Publish a JSON event to the run's Redis pub/sub channel.

    If no Redis client has been registered (e.g. in the API process), this is
    a no-op.  Errors are logged and swallowed — a publish failure must never
    crash the agent pipeline.

    Args:
        run_id:     The run this event belongs to.
        event_type: One of ``"agent_step"``, ``"status_change"``, ``"diff_created"``.
        data:       Serialisable dict of event payload.
    """
    if _redis is None:
        return

    channel = f"run:{run_id}:events"
    payload = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await _redis.publish(channel, json.dumps(payload))
    except Exception:
        logger.warning(
            "Failed to publish run event",
            extra={"run_id": str(run_id), "event_type": event_type},
        )
