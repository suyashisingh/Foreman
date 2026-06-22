"""Reusable FastAPI dependencies.

``get_db``                    — yields an async SQLAlchemy session per request.
``get_current_user``          — validates the Bearer JWT and returns the User.
``get_current_user_optional`` — like get_current_user but returns None if no/bad token.
``get_arq_pool``              — returns the application-scoped ARQ job queue pool.
"""

import uuid
from typing import Any, AsyncGenerator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as _db_session
from app.core.security import decode_access_token
from app.db.models import User

_bearer = HTTPBearer()
_bearer_optional = HTTPBearer(auto_error=False)


async def get_arq_pool(request: Request) -> Any:
    """Return the application-scoped ARQ job queue pool from app state."""
    return request.app.state.arq_pool


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a session from the module-level factory set up during lifespan."""
    if _db_session.async_session_factory is None:
        raise RuntimeError("Database engine has not been initialised.")
    async with _db_session.async_session_factory() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate the Bearer JWT and return the associated User row.

    Raises HTTP 401 on a missing, expired, or otherwise invalid token, and
    also when the token's subject does not match any user in the database.
    """
    _401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _401
    except jwt.InvalidTokenError:
        raise _401

    sub: str | None = payload.get("sub")
    if sub is None:
        raise _401

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise _401

    user = await db.get(User, user_id)
    if user is None:
        raise _401

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401.

    Used for endpoints that serve both public and authenticated callers with
    different data shapes (e.g. global aggregate vs. per-user filtered view).
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        return None

    sub: str | None = payload.get("sub")
    if sub is None:
        return None

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        return None

    return await db.get(User, user_id)
