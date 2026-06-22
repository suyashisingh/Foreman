"""Pydantic schemas for repo registration, retrieval, and search endpoints."""

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


class ChunkSearchResult(BaseModel):
    """One ranked result from GET /api/v1/repos/{id}/search."""

    file_path: str
    symbol_name: str | None
    content: str
    similarity: float  # 1.0 = identical, -1.0 = opposite; higher is more relevant


class CostEstimateOut(BaseModel):
    """Rough pre-run token-cost estimate for a repo."""

    estimated_usd: float
    chunk_count: int
