"""Reusable FastAPI dependencies.

``get_db``          — yields an async SQLAlchemy session per request.
``get_current_user``— validates the Bearer JWT and returns the authenticated User.
"""

import uuid
from typing import AsyncGenerator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as _db_session
from app.core.security import decode_access_token
from app.db.models import User

_bearer = HTTPBearer()


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
