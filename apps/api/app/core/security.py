"""Password hashing and JWT utilities.

Password hashing: pwdlib with the Argon2 backend (via argon2-cffi).
JWT:              PyJWT (HS256 by default, configurable).

Nothing in this module falls back to a hardcoded secret; all secrets come from
``app.core.config.settings``.
"""

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

# Single module-level hasher instance; Argon2Hasher is thread-safe.
_password_hash = PasswordHash([Argon2Hasher()])


def hash_password(plain: str) -> str:
    """Return an Argon2 hash of *plain*."""
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` iff *plain* matches the Argon2 *hashed* value."""
    return _password_hash.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    """Create a signed JWT with *subject* as the ``sub`` claim.

    Expiry is controlled by ``settings.JWT_EXPIRY_MINUTES``.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict:
    """Decode and verify *token*, returning the payload dict.

    Raises ``jwt.ExpiredSignatureError`` if the token has expired, or
    ``jwt.InvalidTokenError`` for any other verification failure.
    """
    return jwt.decode(
        token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
