"""Tests for graph routing logic and sandbox lifecycle in execute_run.

Covers:
- _route_after_tester: all three branches (pass, retry, exhausted).
- execute_run: sandbox created once, killed exactly once, even across retries.
- execute_run: final status set correctly for pass vs. retries-exhausted.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.agents.state import AgentState
from app.db.models import Repo, RepoStatus, Run, RunStatus, User
from app.orchestrator.graph import _route_after_coder, _route_after_tester, build_graph

# ---------------------------------------------------------------------------
# Graph structure tests
# ---------------------------------------------------------------------------


def test_build_graph_has_reviewer_node() -> None:
    """build_graph() includes a reviewer node in the compiled graph."""
    graph = build_graph()
    assert "reviewer" in graph.nodes


# ---------------------------------------------------------------------------
# _route_after_tester unit tests (pure logic, no I/O)
# ---------------------------------------------------------------------------


def _routing_state(**kwargs: Any) -> AgentState:
    """Minimal state for routing tests."""
    import uuid

    base: AgentState = AgentState(
        run_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        issue_text="test",
    )
    base.update(kwargs)  # type: ignore[attr-defined]
    return base


def test_route_after_tester_pass_returns_pass() -> None:
    """test_passed=True → 'pass' regardless of retry_count."""
    state = _routing_state(test_passed=True, retry_count=0)
    assert _route_after_tester(state) == "pass"


def test_route_after_tester_pass_ignores_retry_count() -> None:
    state = _routing_state(test_passed=True, retry_count=5)
    assert _route_after_tester(state) == "pass"


def test_route_after_tester_fail_retries_available() -> None:
    """test_passed=False with retry_count < MAX → 'retry'."""
    with patch("app.orchestrator.graph.settings") as mock_settings:
        mock_settings.MAX_CODER_RETRIES = 2
        state = _routing_state(test_passed=False, retry_count=0)
        assert _route_after_tester(state) == "retry"


def test_route_after_tester_fail_one_retry_left() -> None:
    with patch("app.orchestrator.graph.settings") as mock_settings:
        mock_settings.MAX_CODER_RETRIES = 2
        state = _routing_state(test_passed=False, retry_count=1)
        assert _route_after_tester(state) == "retry"


def test_route_after_tester_fail_retries_exhausted() -> None:
    """test_passed=False with retry_count >= MAX → 'exhausted'."""
    with patch("app.orchestrator.graph.settings") as mock_settings:
        mock_settings.MAX_CODER_RETRIES = 2
        state = _routing_state(test_passed=False, retry_count=2)
        assert _route_after_tester(state) == "exhausted"


def test_route_after_tester_fail_beyond_max() -> None:
    with patch("app.orchestrator.graph.settings") as mock_settings:
        mock_settings.MAX_CODER_RETRIES = 2
        state = _routing_state(test_passed=False, retry_count=3)
        assert _route_after_tester(state) == "exhausted"


# ---------------------------------------------------------------------------
# execute_run sandbox lifecycle tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def exec_run(db) -> Run:
    """Seed a User + Repo + Run for execute_run tests."""
    user = User(
        email="graph_test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Graph",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="testrepo",
        clone_url="https://github.com/example/repo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    run = Run(
        user_id=user.id,
        repo_id=repo.id,
        issue_text="A test issue",
        status=RunStatus.pending,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_sandbox_created_and_killed_exactly_once(
    exec_run: Run, session_factory
) -> None:
    """execute_run creates the sandbox once and kills it once in finally."""
    sandbox_mock = AsyncMock()
    sandbox_mock.sandbox_id = "sb-lifecycle-test"
    sandbox_mock.kill = AsyncMock()

    final_state = {
        "plan": {"steps": []},
        "diffs": [],
        "test_passed": True,
        "retry_count": 0,
    }

    with (
        patch("app.workers.tasks.AsyncSandbox") as mock_sb_cls,
        patch("app.workers.tasks.build_graph") as mock_build_graph,
        patch("app.workers.tasks.settings") as mock_settings,
    ):
        mock_settings.E2B_API_KEY = "dummy"
        mock_sb_cls.create = AsyncMock(return_value=sandbox_mock)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)
        mock_build_graph.return_value = mock_graph

        ctx = {"session_factory": session_factory}
        from app.workers.tasks import execute_run

        await execute_run(ctx, str(exec_run.id))

    mock_sb_cls.create.assert_awaited_once()
    sandbox_mock.kill.assert_awaited_once()


@pytest.mark.asyncio
async def test_sandbox_killed_even_on_graph_exception(
    exec_run: Run, session_factory
) -> None:
    """sandbox.kill() is called in finally even when graph.ainvoke raises."""
    sandbox_mock = AsyncMock()
    sandbox_mock.sandbox_id = "sb-exception-test"
    sandbox_mock.kill = AsyncMock()

    with (
        patch("app.workers.tasks.AsyncSandbox") as mock_sb_cls,
        patch("app.workers.tasks.build_graph") as mock_build_graph,
        patch("app.workers.tasks.settings") as mock_settings,
    ):
        mock_settings.E2B_API_KEY = "dummy"
        mock_sb_cls.create = AsyncMock(return_value=sandbox_mock)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("graph exploded"))
        mock_build_graph.return_value = mock_graph

        ctx = {"session_factory": session_factory}
        from app.workers.tasks import execute_run

        await execute_run(ctx, str(exec_run.id))  # should NOT re-raise

    sandbox_mock.kill.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_run_sets_awaiting_approval_on_test_pass(
    exec_run: Run, session_factory, db
) -> None:
    """When tests pass, run status is set to awaiting_approval."""
    sandbox_mock = AsyncMock()
    sandbox_mock.sandbox_id = "sb-pass"
    sandbox_mock.kill = AsyncMock()

    final_state = {
        "plan": {"steps": []},
        "diffs": [],
        "test_passed": True,
        "retry_count": 0,
    }

    with (
        patch("app.workers.tasks.AsyncSandbox") as mock_sb_cls,
        patch("app.workers.tasks.build_graph") as mock_build_graph,
        patch("app.workers.tasks.settings") as mock_settings,
    ):
        mock_settings.E2B_API_KEY = "dummy"
        mock_sb_cls.create = AsyncMock(return_value=sandbox_mock)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)
        mock_build_graph.return_value = mock_graph

        ctx = {"session_factory": session_factory}
        from app.workers.tasks import execute_run

        await execute_run(ctx, str(exec_run.id))

    await db.refresh(exec_run)
    assert exec_run.status == RunStatus.awaiting_approval


@pytest.mark.asyncio
async def test_execute_run_sets_failed_when_retries_exhausted(
    exec_run: Run, session_factory, db
) -> None:
    """When test_passed=False (retries exhausted), run status is set to failed."""
    sandbox_mock = AsyncMock()
    sandbox_mock.sandbox_id = "sb-fail"
    sandbox_mock.kill = AsyncMock()

    final_state = {
        "plan": {"steps": []},
        "diffs": [],
        "test_passed": False,
        "retry_count": 2,
        "test_output": "FAILED test_foo.py::test_bar\n2 failed",
    }

    with (
        patch("app.workers.tasks.AsyncSandbox") as mock_sb_cls,
        patch("app.workers.tasks.build_graph") as mock_build_graph,
        patch("app.workers.tasks.settings") as mock_settings,
    ):
        mock_settings.E2B_API_KEY = "dummy"
        mock_sb_cls.create = AsyncMock(return_value=sandbox_mock)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)
        mock_build_graph.return_value = mock_graph

        ctx = {"session_factory": session_factory}
        from app.workers.tasks import execute_run

        await execute_run(ctx, str(exec_run.id))

    await db.refresh(exec_run)
    assert exec_run.status == RunStatus.failed


# ---------------------------------------------------------------------------
# _route_after_coder unit tests (pure logic, no I/O)
# ---------------------------------------------------------------------------


def test_route_after_coder_no_diffs_returns_no_diffs() -> None:
    """Empty diffs → 'no_diffs' (graph routes to END, tasks.py marks failed)."""
    state = _routing_state(diffs=[])
    assert _route_after_coder(state) == "no_diffs"


def test_route_after_coder_with_diffs_returns_tester() -> None:
    """Non-empty diffs → 'tester' (normal path through Tester node)."""
    state = _routing_state(diffs=[{"file_path": "foo.py", "patch": "---\n+++"}])
    assert _route_after_coder(state) == "tester"


def test_route_after_coder_missing_diffs_key_returns_no_diffs() -> None:
    """State with no 'diffs' key at all (falsy) → 'no_diffs'."""
    state = _routing_state()
    assert _route_after_coder(state) == "no_diffs"


# ---------------------------------------------------------------------------
# execute_run zero-diffs handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_run_sets_failed_with_zero_diffs(
    exec_run: Run, session_factory, db
) -> None:
    """When the graph ends with diffs=[] and test_passed=None, run is marked failed
    with a message indicating the coder made no file changes."""
    sandbox_mock = AsyncMock()
    sandbox_mock.sandbox_id = "sb-zero-diffs"
    sandbox_mock.kill = AsyncMock()

    final_state = {
        "plan": {"steps": []},
        "diffs": [],
        "test_passed": None,
        "retry_count": 0,
    }

    with (
        patch("app.workers.tasks.AsyncSandbox") as mock_sb_cls,
        patch("app.workers.tasks.build_graph") as mock_build_graph,
        patch("app.workers.tasks.settings") as mock_settings,
    ):
        mock_settings.E2B_API_KEY = "dummy"
        mock_sb_cls.create = AsyncMock(return_value=sandbox_mock)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)
        mock_build_graph.return_value = mock_graph

        ctx = {"session_factory": session_factory}
        from app.workers.tasks import execute_run

        await execute_run(ctx, str(exec_run.id))

    await db.refresh(exec_run)
    assert exec_run.status == RunStatus.failed
    assert exec_run.error_message is not None
    assert "no file changes" in exec_run.error_message


@pytest.mark.asyncio
async def test_execute_run_retries_exhausted_uses_test_message_not_zero_diffs(
    exec_run: Run, session_factory, db
) -> None:
    """diffs present + test_passed=False → 'Tests failed' message, not zero-diffs."""
    sandbox_mock = AsyncMock()
    sandbox_mock.sandbox_id = "sb-test-fail"
    sandbox_mock.kill = AsyncMock()

    final_state = {
        "plan": {"steps": []},
        "diffs": [{"file_path": "foo.py", "patch": "---\n+++"}],
        "test_passed": False,
        "retry_count": 2,
        "test_output": "FAILED test_foo.py::test_bar\n2 failed",
    }

    with (
        patch("app.workers.tasks.AsyncSandbox") as mock_sb_cls,
        patch("app.workers.tasks.build_graph") as mock_build_graph,
        patch("app.workers.tasks.settings") as mock_settings,
    ):
        mock_settings.E2B_API_KEY = "dummy"
        mock_sb_cls.create = AsyncMock(return_value=sandbox_mock)
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value=final_state)
        mock_build_graph.return_value = mock_graph

        ctx = {"session_factory": session_factory}
        from app.workers.tasks import execute_run

        await execute_run(ctx, str(exec_run.id))

    await db.refresh(exec_run)
    assert exec_run.status == RunStatus.failed
    assert exec_run.error_message is not None
    assert "Tests failed" in exec_run.error_message
    assert "no file changes" not in exec_run.error_message
