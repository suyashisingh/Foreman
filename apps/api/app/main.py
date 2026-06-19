"""FastAPI application factory and lifespan management."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import close_engine, init_engine
from app.routers import auth, health, repos

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of shared resources."""
    configure_logging(settings.LOG_LEVEL)

    logger.info("Starting Foreman API", extra={"environment": settings.ENVIRONMENT})

    init_engine()
    # from_url is synchronous; it returns a Redis client that uses async I/O.
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    yield

    logger.info("Shutting down Foreman API")
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
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(repos.router)

    return application


app = create_app()
