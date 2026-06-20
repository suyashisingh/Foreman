"""Unit tests for the Tester LangGraph node (tester.py).

The e2b sandbox is fully mocked — no live services required.
Tests cover:
- Run status transition to ``testing``.
- Pass/fail determination from exit_code.
- TestAttempt row persistence.
- AgentStep row persistence with correct step_index.
- test_output assembled from stdout + stderr.
- attempt_number computed from retry_count.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.state import AgentState
from app.agents.tester import tester_node
from app.db.models import (
    AgentRole,
    AgentStep,
    Repo,
    RepoStatus,
    Run,
    RunStatus,
    TestAttempt,
    User,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox_mock(
    exit_code: int = 0,
    stdout: str = "1 passed",
    stderr: str = "",
) -> AsyncMock:
    """Build a mocked sandbox whose commands.run mirrors real e2b behaviour.

    The real e2b SDK raises CommandExitException for non-zero exit codes and
    returns a CommandResult object when exit_code == 0.
    """
    from e2b import CommandResult
    from e2b.sandbox_async.commands.command_handle import CommandExitException

    sandbox = AsyncMock()
    sandbox.sandbox_id = "tester-sandbox-xyz"

    def _run_side_effect(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        if exit_code != 0:
            raise CommandExitException(
                stderr=stderr, stdout=stdout, exit_code=exit_code, error=None
            )
        r = MagicMock(spec=CommandResult)
        r.stdout = stdout
        r.stderr = stderr
        r.exit_code = exit_code
        r.error = None
        return r

    sandbox.commands.run = AsyncMock(side_effect=_run_side_effect)
    sandbox.kill = AsyncMock()
    return sandbox


def _tester_state(run: Run, sandbox: Any, retry_count: int = 0) -> AgentState:
    return AgentState(
        run_id=run.id,
        repo_id=run.repo_id,
        issue_text="test issue",
        retrieved_context=[],
        plan=None,
        diffs=[],
        current_agent="coder",
        retry_count=retry_count,
        error=None,
        sandbox=sandbox,
        test_passed=None,
        test_output=None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def tester_run(db) -> Run:
    """Seed a User + Repo + Run for tester tests."""
    user = User(
        email="tester_test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Tester",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="myrepo",
        clone_url="https://github.com/example/myrepo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    run = Run(
        user_id=user.id,
        repo_id=repo.id,
        issue_text="Fix the failing test",
        status=RunStatus.coding,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tester_sets_run_status_to_testing(
    tester_run: Run, session_factory, db
) -> None:
    """tester_node transitions run.status to testing before running pytest."""
    sandbox = _make_sandbox_mock(exit_code=0, stdout="1 passed")

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        await tester_node(_tester_state(tester_run, sandbox))

    await db.refresh(tester_run)
    # Status transitions: tester sets "testing"; final status is set by tasks.py.
    # After tester_node runs, the DB status is "testing".
    assert tester_run.status == RunStatus.testing


@pytest.mark.asyncio
async def test_tester_pass_when_exit_code_zero(
    tester_run: Run, session_factory
) -> None:
    """exit_code=0 → test_passed=True in returned state."""
    sandbox = _make_sandbox_mock(exit_code=0, stdout="2 passed in 0.1s")

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        result = await tester_node(_tester_state(tester_run, sandbox))

    assert result["test_passed"] is True
    assert result["current_agent"] == "tester"


@pytest.mark.asyncio
async def test_tester_fail_when_exit_code_nonzero(
    tester_run: Run, session_factory
) -> None:
    """exit_code=1 → test_passed=False in returned state."""
    sandbox = _make_sandbox_mock(
        exit_code=1,
        stdout="FAILED test_foo.py::test_bar - AssertionError\n1 failed in 0.2s",
    )

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        result = await tester_node(_tester_state(tester_run, sandbox))

    assert result["test_passed"] is False


@pytest.mark.asyncio
async def test_tester_test_output_in_state(tester_run: Run, session_factory) -> None:
    """test_output in returned state contains pytest stdout."""
    sandbox = _make_sandbox_mock(
        exit_code=1,
        stdout="FAILED test_x.py::test_y\n1 failed",
        stderr="",
    )

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        result = await tester_node(_tester_state(tester_run, sandbox))

    assert "FAILED test_x.py::test_y" in result["test_output"]


@pytest.mark.asyncio
async def test_tester_test_output_includes_stderr(
    tester_run: Run, session_factory
) -> None:
    """When pytest writes to stderr, it is appended to test_output."""
    sandbox = _make_sandbox_mock(
        exit_code=1,
        stdout="0 passed",
        stderr="ModuleNotFoundError: No module named 'mymodule'",
    )

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        result = await tester_node(_tester_state(tester_run, sandbox))

    assert "ModuleNotFoundError" in result["test_output"]


@pytest.mark.asyncio
async def test_tester_persists_test_attempt(
    tester_run: Run, session_factory, db
) -> None:
    """tester_node inserts a TestAttempt row with correct fields."""
    sandbox = _make_sandbox_mock(exit_code=0, stdout="3 passed in 0.5s", stderr="")

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        await tester_node(_tester_state(tester_run, sandbox, retry_count=0))

    attempts = (
        (
            await db.execute(
                select(TestAttempt).where(TestAttempt.run_id == tester_run.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.passed is True
    assert attempt.attempt_number == 1
    assert attempt.run_id == tester_run.id
    assert "3 passed" in (attempt.stdout or "")


@pytest.mark.asyncio
async def test_tester_attempt_number_on_retry(
    tester_run: Run, session_factory, db
) -> None:
    """attempt_number increments correctly: retry_count=1 → attempt_number=2."""
    sandbox = _make_sandbox_mock(exit_code=1, stdout="1 failed")

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        await tester_node(_tester_state(tester_run, sandbox, retry_count=1))

    attempts = (
        (
            await db.execute(
                select(TestAttempt).where(TestAttempt.run_id == tester_run.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(attempts) == 1
    assert attempts[0].attempt_number == 2
    assert attempts[0].passed is False


@pytest.mark.asyncio
async def test_tester_logs_agent_step(tester_run: Run, session_factory, db) -> None:
    """tester_node persists an AgentStep row with agent=tester."""
    sandbox = _make_sandbox_mock(exit_code=0, stdout="1 passed")

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        await tester_node(_tester_state(tester_run, sandbox, retry_count=0))

    steps = (
        (
            await db.execute(
                select(AgentStep).where(
                    AgentStep.run_id == tester_run.id,
                    AgentStep.agent == AgentRole.tester,
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(steps) == 1
    step = steps[0]
    assert step.agent == AgentRole.tester
    assert step.step_index == 2  # retry_count=0 → 2 + 2*0 = 2
    assert step.output["passed"] is True


@pytest.mark.asyncio
async def test_tester_step_index_on_retry(tester_run: Run, session_factory, db) -> None:
    """step_index is 2 + 2*retry_count — correct on both first and retry runs."""
    sandbox = _make_sandbox_mock(exit_code=0, stdout="1 passed")

    with patch("app.agents.tester._db_session.async_session_factory", session_factory):
        await tester_node(_tester_state(tester_run, sandbox, retry_count=1))

    steps = (
        (await db.execute(select(AgentStep).where(AgentStep.run_id == tester_run.id)))
        .scalars()
        .all()
    )

    assert len(steps) == 1
    assert steps[0].step_index == 4  # 2 + 2*1 = 4
