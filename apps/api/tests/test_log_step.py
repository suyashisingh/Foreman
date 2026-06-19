"""Tests for the log_agent_step helper (orchestrator/logging.py)."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.models import AgentRole, AgentStep, Repo, RepoStatus, Run, RunStatus, User
from app.orchestrator.logging import log_agent_step


@pytest_asyncio.fixture
async def run_for_logging(db):
    """A minimal User+Repo+Run seeded for log_agent_step tests."""
    user = User(
        email="logtest@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="LogTest",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="log-repo",
        clone_url="https://github.com/x/y.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    run = Run(
        user_id=user.id,
        repo_id=repo.id,
        issue_text="Test log step",
        status=RunStatus.planning,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_log_agent_step_writes_row(run_for_logging, db):
    """log_agent_step persists a correct AgentStep row."""
    step = await log_agent_step(
        db=db,
        run_id=run_for_logging.id,
        agent=AgentRole.planner,
        step_index=0,
        input_data={"issue_text": "Hello", "retrieved_chunk_count": 5},
        output_data={"steps": [], "rationale": "No changes needed"},
        tool_calls=[],
        token_usage={"input_tokens": 200, "output_tokens": 80},
        latency_ms=750,
    )

    # Verify returned object
    assert step.id is not None
    assert step.run_id == run_for_logging.id
    assert step.agent == AgentRole.planner
    assert step.step_index == 0
    assert step.latency_ms == 750
    assert step.token_usage == {"input_tokens": 200, "output_tokens": 80}
    assert step.tool_calls == []

    # Verify it is persisted by re-reading from DB
    fetched = await db.get(AgentStep, step.id)
    assert fetched is not None
    assert fetched.output == {"steps": [], "rationale": "No changes needed"}
    assert fetched.input == {"issue_text": "Hello", "retrieved_chunk_count": 5}


@pytest.mark.asyncio
async def test_log_agent_step_increments_index(run_for_logging, db):
    """Two calls with step_index 0 and 1 produce two distinct rows."""
    await log_agent_step(
        db=db,
        run_id=run_for_logging.id,
        agent=AgentRole.planner,
        step_index=0,
        input_data={},
        output_data={"rationale": "plan"},
        tool_calls=[],
        token_usage={"input_tokens": 10, "output_tokens": 5},
        latency_ms=100,
    )
    await log_agent_step(
        db=db,
        run_id=run_for_logging.id,
        agent=AgentRole.coder,
        step_index=1,
        input_data={},
        output_data={"diff": "patch"},
        tool_calls=[{"name": "write_file"}],
        token_usage={"input_tokens": 20, "output_tokens": 15},
        latency_ms=200,
    )

    rows = (
        (
            await db.execute(
                select(AgentStep)
                .where(AgentStep.run_id == run_for_logging.id)
                .order_by(AgentStep.step_index)
            )
        )
        .scalars()
        .all()
    )

    assert len(rows) == 2
    assert rows[0].step_index == 0
    assert rows[1].step_index == 1
    assert rows[0].agent == AgentRole.planner
    assert rows[1].agent == AgentRole.coder
