"""Pydantic schemas for authentication endpoints.

``UserOut`` intentionally excludes ``password_hash`` — the field is not
present in the schema at all, so it can never leak through accidental
``model_validate`` calls even if the ORM model is passed directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for POST /api/v1/auth/register."""

    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None


class UserLogin(BaseModel):
    """Payload for POST /api/v1/auth/login."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """JWT response returned after successful register or login."""

    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """Safe public representation of a user — never includes password_hash."""

    id: uuid.UUID
    email: str
    name: str | None
    created_at: datetime

    # Allow construction directly from ORM model instances.
    model_config = ConfigDict(from_attributes=True)
