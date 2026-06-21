"""Pydantic schemas for the /api/v1/runs endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.models import AgentRole, RunStatus


class RunCreate(BaseModel):
    """Payload for POST /api/v1/runs."""

    repo_id: uuid.UUID
    issue_text: str


class AgentStepOut(BaseModel):
    """One agent step as returned in GET /api/v1/runs/{id}."""

    id: uuid.UUID
    agent: AgentRole
    step_index: int
    input: dict[str, Any]
    output: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    token_usage: dict[str, Any]
    latency_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReviewOut(BaseModel):
    """Structured Reviewer output surfaced in GET /api/v1/runs/{id}."""

    summary: str
    risk_level: str
    risk_notes: str
    pr_title: str
    pr_description: str


class DiffOut(BaseModel):
    """One file diff awaiting human approval."""

    id: uuid.UUID
    file_path: str
    patch: str
    approved: bool

    model_config = ConfigDict(from_attributes=True)


class RunOut(BaseModel):
    """Summary run representation for list endpoints."""

    id: uuid.UUID
    repo_id: uuid.UUID
    status: RunStatus
    issue_text: str
    created_at: datetime
    completed_at: datetime | None
    rejection_reason: str | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RunDetail(RunOut):
    """Full run detail including all logged agent steps, ordered by step_index."""

    agent_steps: list[AgentStepOut]
    review: ReviewOut | None = None
    diffs: list[DiffOut] = []


class RunRejectBody(BaseModel):
    """Optional body for POST /api/v1/runs/{id}/reject."""

    reason: str | None = None
