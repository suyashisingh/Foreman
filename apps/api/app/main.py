"""FastAPI application factory and lifespan management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from arq import Worker, create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import close_engine, init_engine
from app.routers import auth, benchmark, health, repos, runs, system, ws
from app.workers.settings import WorkerSettings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of shared resources."""
    configure_logging(settings.LOG_LEVEL)

    logger.info("Starting Foreman API", extra={"environment": settings.ENVIRONMENT})

    init_engine()

    # Redis client used by the health-check readiness probe.
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    # ARQ pool used by route handlers to enqueue background jobs.
    # This is a separate connection from app.state.redis — ARQ manages its own
    # protocol framing and should not share the general-purpose client.
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))

    # Render's free tier only allows one web service, so the ARQ worker runs
    # as a background task inside the API process instead of a separate
    # Render worker service. Harmless to also run this locally alongside a
    # standalone `uv run arq ...` worker — ARQ workers coordinate over Redis.
    async def run_worker() -> None:
        worker = Worker(
            functions=WorkerSettings.functions,
            redis_settings=WorkerSettings.redis_settings,
            max_jobs=WorkerSettings.max_jobs,
            job_timeout=WorkerSettings.job_timeout,
            on_startup=WorkerSettings.on_startup,
            on_shutdown=WorkerSettings.on_shutdown,
            # We manage the worker's lifecycle ourselves via the FastAPI
            # lifespan (cancel + manual cleanup below). Left at its True
            # default, arq registers its own SIGINT/SIGTERM handlers on
            # this loop, which both hijacks uvicorn's own shutdown signal
            # handling and crashes outright when the loop isn't running on
            # the main thread (e.g. FastAPI's TestClient, which runs the
            # app in a background thread).
            handle_signals=False,
        )
        app.state.worker = worker
        await worker.async_run()

    app.state.worker_task = asyncio.create_task(run_worker())

    yield

    logger.info("Shutting down Foreman API")
    if hasattr(app.state, "worker_task"):
        app.state.worker_task.cancel()
        try:
            await app.state.worker_task
        except asyncio.CancelledError:
            pass
        # Replicates arq's Worker.close(), minus its `handle_sig(SIGUSR1)`
        # call — SIGUSR1 doesn't exist on Windows, and we've already
        # cancelled the worker above, so that call would be redundant here
        # even on POSIX. async_run() itself doesn't close the worker's own
        # Redis pool or run on_shutdown (which disposes the DB engine), so
        # both are done explicitly.
        if hasattr(app.state, "worker"):
            worker = app.state.worker
            for job_task in worker.tasks.values():
                if not job_task.done():
                    job_task.cancel()
            if worker.pool is not None:
                await worker.pool.delete(worker.health_check_key)
                if worker.on_shutdown:
                    await worker.on_shutdown(worker.ctx)
                await worker.pool.close(close_connection_pool=True)
    await app.state.arq_pool.aclose()
    await app.state.redis.aclose()
    await close_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title="Foreman API",
        description="Autonomous multi-agent software engineering platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(repos.router)
    application.include_router(runs.router)
    application.include_router(ws.router)
    application.include_router(benchmark.router)
    application.include_router(system.router)

    return application


app = create_app()
