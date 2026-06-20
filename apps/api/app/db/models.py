"""SQLAlchemy 2.0 ORM models for the Foreman platform.

Import this module wherever you need to reference model classes, and always
import it in Alembic's env.py so autogenerate can discover every table.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# ---------------------------------------------------------------------------
# Python-level enum definitions — used both by the ORM and by application code
# ---------------------------------------------------------------------------


class RepoStatus(str, enum.Enum):
    """Lifecycle states for a registered repository."""

    pending = "pending"
    cloning = "cloning"
    chunking = "chunking"
    embedding = "embedding"
    ready = "ready"
    failed = "failed"


class RunStatus(str, enum.Enum):
    """Lifecycle states for an agent run."""

    pending = "pending"
    planning = "planning"
    coding = "coding"
    testing = "testing"
    reviewing = "reviewing"
    passed = "passed"
    failed = "failed"
    awaiting_approval = "awaiting_approval"
    rejected = "rejected"


class AgentRole(str, enum.Enum):
    """Agent roles that can produce a step in a run."""

    planner = "planner"
    coder = "coder"
    tester = "tester"
    reviewer = "reviewer"


# ---------------------------------------------------------------------------
# SQLAlchemy Enum type objects (native Postgres ENUM, not VARCHAR)
# ---------------------------------------------------------------------------

_repo_status_pg = Enum(RepoStatus, name="repo_status", create_type=True)
_run_status_pg = Enum(RunStatus, name="run_status", create_type=True)
_agent_role_pg = Enum(AgentRole, name="agent_role", create_type=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class User(Base):
    """Platform users. Password is stored as an Argon2 hash; never plaintext."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(1024), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    repos: Mapped[list[Repo]] = relationship(back_populates="user")
    runs: Mapped[list[Run]] = relationship(back_populates="user")

    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)


class Repo(Base):
    """A Git repository registered by a user."""

    __tablename__ = "repos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    clone_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="main"
    )
    status: Mapped[RepoStatus] = mapped_column(
        _repo_status_pg, nullable=False, server_default="pending"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="repos")
    runs: Mapped[list[Run]] = relationship(back_populates="repo")
    chunks: Mapped[list[RepoChunk]] = relationship(back_populates="repo")


class Run(Base):
    """A single agent run against a repo and issue."""

    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    )
    issue_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RunStatus] = mapped_column(_run_status_pg, nullable=False)
    sandbox_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="runs")
    repo: Mapped[Repo] = relationship(back_populates="runs")
    agent_steps: Mapped[list[AgentStep]] = relationship(
        back_populates="run", order_by="AgentStep.step_index"
    )
    test_attempts: Mapped[list[TestAttempt]] = relationship(back_populates="run")
    diffs: Mapped[list[Diff]] = relationship(back_populates="run")


class AgentStep(Base):
    """One step produced by an agent during a run (input → LLM call → output)."""

    __tablename__ = "agent_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    agent: Mapped[AgentRole] = mapped_column(_agent_role_pg, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tool_calls: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="agent_steps")


class TestAttempt(Base):
    """One execution of the test suite during a run."""

    __tablename__ = "test_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="test_attempts")


class Diff(Base):
    """A file-level diff produced by an agent, awaiting human review."""

    __tablename__ = "diffs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    patch: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    run: Mapped[Run] = relationship(back_populates="diffs")


class RepoChunk(Base):
    """A code chunk extracted from a repo, with a vector embedding for RAG."""

    __tablename__ = "repo_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # voyage-code-3 outputs 1024-dimensional embeddings by default.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)

    repo: Mapped[Repo] = relationship(back_populates="chunks")


class BenchmarkRun(Base):
    """A batch evaluation run against the benchmark dataset."""

    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    results: Mapped[list[BenchmarkResult]] = relationship(
        back_populates="benchmark_run"
    )


class BenchmarkResult(Base):
    """One task's result within a benchmark run."""

    __tablename__ = "benchmark_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts_to_pass: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    time_to_green_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    benchmark_run: Mapped[BenchmarkRun] = relationship(back_populates="results")
