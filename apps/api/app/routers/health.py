"""Health and readiness endpoints.

/health  — liveness probe. Returns 200 immediately; no I/O.
/ready   — readiness probe. Attempts a trivial DB query and a Redis PING.
           Returns 200 when both succeed, 503 otherwise.
"""

import logging

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

import app.db.session as _db_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    """Return 200 immediately to signal that the process is alive."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def readiness(request: Request, response: Response) -> dict:
    """Return 200 when Postgres and Redis are reachable, 503 otherwise."""
    errors: list[str] = []

    # --- Database check ---
    # Access via module reference so the lifespan-set value is always current.
    factory = _db_session.async_session_factory
    if factory is None:
        errors.append("db: engine not initialised")
    else:
        try:
            async with factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            logger.warning("Readiness DB check failed: %s", exc)
            errors.append(f"db: {exc}")

    # --- Redis check ---
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        errors.append("redis: client not initialised")
    else:
        try:
            await redis.ping()
        except Exception as exc:
            logger.warning("Readiness Redis check failed: %s", exc)
            errors.append(f"redis: {exc}")

    if errors:
        response.status_code = 503
        return {"status": "unavailable", "errors": errors}

    return {"status": "ready"}
