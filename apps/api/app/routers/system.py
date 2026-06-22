"""System health and configuration status endpoint.

GET /api/v1/system/status  — no auth required (public, like /benchmark/results).
Reports DB reachability, Redis reachability, and API key presence (never the
actual key values).  Designed for the Settings page.
"""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

import app.db.session as _db_session
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class SystemStatus(BaseModel):
    database_ok: bool
    redis_ok: bool
    gemini_key_configured: bool
    voyage_key_configured: bool
    e2b_key_configured: bool
    gemini_model: str


@router.get(
    "/status",
    response_model=SystemStatus,
    summary="System health and API key presence (no auth required)",
)
async def get_system_status(request: Request) -> SystemStatus:
    """Return infrastructure status and key presence without revealing key values.

    Database and Redis are tested with cheap real pings.  API keys are only
    checked for presence (bool), never echoed back.
    """
    # --- Database ping ---
    db_ok = False
    factory = _db_session.async_session_factory
    if factory is not None:
        try:
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            logger.warning("system/status: DB ping failed")

    # --- Redis ping (uses the shared client from app.state) ---
    redis_ok = False
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            redis_ok = True
        except Exception:
            logger.warning("system/status: Redis ping failed")

    return SystemStatus(
        database_ok=db_ok,
        redis_ok=redis_ok,
        gemini_key_configured=bool(getattr(settings, "GEMINI_API_KEY", "")),
        voyage_key_configured=bool(getattr(settings, "VOYAGE_API_KEY", "")),
        e2b_key_configured=bool(getattr(settings, "E2B_API_KEY", "")),
        gemini_model=settings.GEMINI_MODEL,
    )
