"""Authentication endpoints: register, login, me."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import Token, UserCreate, UserLogin, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and receive a JWT",
)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Create a new user account.

    Returns a signed JWT on success. Rejects duplicate e-mail addresses with
    HTTP 409 rather than exposing a raw database error.
    """
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Rare race condition: two simultaneous registrations with the same email.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )
    await db.refresh(user)

    logger.info("New user registered", extra={"user_id": str(user.id)})
    return Token(access_token=create_access_token(str(user.id)))


@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate and receive a JWT",
)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Verify credentials and return a signed JWT.

    The error message is intentionally generic — we do not reveal whether
    the email or the password was wrong.
    """
    _bad = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials.",
    )

    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        raise _bad

    if not verify_password(body.password, user.password_hash):
        raise _bad

    logger.info("User authenticated", extra={"user_id": str(user.id)})
    return Token(access_token=create_access_token(str(user.id)))


@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the authenticated user's profile",
)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Require a valid JWT and return the caller's public profile."""
    return UserOut.model_validate(current_user)
