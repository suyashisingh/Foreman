"""ARQ WorkerSettings: Redis connection, registered tasks, and lifecycle hooks.

Run the worker locally with:

    uv run arq app.workers.settings.WorkerSettings
"""

import logging

import redis.asyncio as aioredis
from arq.connections import RedisSettings

from app.core.config import settings as app_settings
from app.db import session as _db_session
from app.db.session import close_engine, init_engine
from app.orchestrator import events as _events
from app.workers.tasks import execute_run, ingest_repo

logger = logging.getLogger(__name__)


async def on_startup(ctx: dict) -> None:
    """Initialise shared resources for the worker process."""
    logger.info("ARQ worker starting up")
    init_engine()
    ctx["session_factory"] = _db_session.async_session_factory

    # Dedicated Redis client for event publishing (separate from ARQ's pool).
    redis_client = aioredis.from_url(app_settings.REDIS_URL, decode_responses=True)
    ctx["redis"] = redis_client
    _events.set_redis_client(redis_client)


async def on_shutdown(ctx: dict) -> None:
    """Dispose shared resources on worker shutdown."""
    logger.info("ARQ worker shutting down")
    await close_engine()
    if "redis" in ctx:
        await ctx["redis"].aclose()


class WorkerSettings:
    """ARQ worker configuration.

    Run with: ``uv run arq app.workers.settings.WorkerSettings``
    """

    redis_settings: RedisSettings = RedisSettings.from_dsn(app_settings.REDIS_URL)

    functions = [ingest_repo, execute_run]

    # staticmethod so pyright doesn't treat `ctx` as an implicit `self` when
    # these are accessed unbound via the class (both arq's own CLI and
    # app/main.py's in-process worker do `WorkerSettings.on_startup`, never
    # through an instance).
    on_startup = staticmethod(on_startup)
    on_shutdown = staticmethod(on_shutdown)

    # Allow up to 4 concurrent ingestion jobs.  Each job is mostly I/O-bound
    # (git clone + Voyage API), so concurrency is cheap.
    max_jobs: int = 4

    # 5 minutes — generous enough for a large repo clone + embed batch.
    job_timeout: int = 300

    # Keep job results (success/failure) for 1 hour for debugging.
    keep_result: int = 3600
