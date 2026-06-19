"""Pydantic schemas for repo registration and retrieval endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import RepoStatus


class RepoCreate(BaseModel):
    """Payload for POST /api/v1/repos."""

    name: str
    # Plain str rather than HttpUrl so SSH clone URLs are accepted too.
    clone_url: str
    default_branch: str = "main"


class RepoOut(BaseModel):
    """Repo representation returned in list endpoints."""

    id: uuid.UUID
    name: str
    clone_url: str
    default_branch: str
    status: RepoStatus
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RepoDetail(RepoOut):
    """Extended repo representation that includes the stored chunk count."""

    chunk_count: int
