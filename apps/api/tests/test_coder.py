"""Unit tests for the Coder LangGraph node (coder.py) and tool executor (tools.py).

The e2b sandbox and Gemini API are fully mocked — no live services required.
Tests cover:
- The tool-use loop (tool calls executed, results fed back).
- The MAX_CODER_TOOL_ITERATIONS bound (loop exits gracefully when hit).
- Per-file diff persistence to the ``diffs`` table.
- Sandbox cleanup on both success and failure (kill always called in finally).
- Each tool function (read_file, write_file, list_files) in isolation.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.coder import _build_coder_prompt, _parse_diff, coder_node
from app.agents.state import AgentState
from app.agents.tools import execute_tool
from app.db.models import AgentRole, AgentStep, Diff, Repo, RepoStatus, Run, RunStatus, User


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _make_sandbox_mock() -> AsyncMock:
    """Construct a fully-mocked e2b AsyncSandbox."""
    from e2b import CommandResult

    sandbox = AsyncMock()
    sandbox.sandbox_id = "test-sandbox-abc123"

    # Default: clone succeeds, git diff returns empty
    def _run_side_effect(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        result = MagicMock(spec=CommandResult)
        result.stdout = ""
        result.stderr = ""
        result.exit_code = 0
        result.error = None
        return result

    sandbox.commands.run = AsyncMock(side_effect=_run_side_effect)
    sandbox.files.read = AsyncMock(return_value="# original content\n")
    sandbox.files.write = AsyncMock(return_value=MagicMock())
    sandbox.files.list = AsyncMock(return_value=[])
    sandbox.kill = AsyncMock()
    return sandbox


def _make_text_response(text: str = "Done.") -> MagicMock:
    """Mock Gemini response with no function calls (signals the model is done)."""
    part = MagicMock()
    part.function_call = None
    part.text = text

    content = MagicMock()
    content.role = "model"
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.prompt_token_count = 100
    usage.candidates_token_count = 40

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


def _make_fn_call_response(name: str, args: dict[str, Any]) -> MagicMock:
    """Mock Gemini response with a single function call part."""
    fc = MagicMock()
    fc.name = name
    fc.id = None
    fc.args = args

    part = MagicMock()
    part.function_call = fc
    part.text = None

    content = MagicMock()
    content.role = "model"
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    usage = MagicMock()
    usage.prompt_token_count = 120
    usage.candidates_token_count = 30

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage
    return response


def _make_client_mock(*responses: MagicMock) -> MagicMock:
    """Construct a mock genai.Client whose generate_content returns *responses* in order."""
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=list(responses))
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def coder_run(db) -> Run:
    """Seed a User + Repo + Run in the test DB for coder tests."""
    user = User(
        email="coder_test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Coder",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="iniconfig",
        clone_url="https://github.com/pytest-dev/iniconfig.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    run = Run(
        user_id=user.id,
        repo_id=repo.id,
        issue_text="Add a hello() function",
        status=RunStatus.planning,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


def _base_state(run: Run) -> AgentState:
    return AgentState(
        run_id=run.id,
        repo_id=run.repo_id,
        issue_text=run.issue_text,
        retrieved_context=[],
        plan={
            "steps": [
                {
                    "file_path": "hello.py",
                    "action": "create",
                    "description": "Add hello() function",
                }
            ],
            "rationale": "Simple addition",
        },
        diffs=[],
        current_agent="planner",
        retry_count=0,
        error=None,
    )


# ---------------------------------------------------------------------------
# _build_coder_prompt unit tests (pure, no I/O)
# ---------------------------------------------------------------------------


def test_build_coder_prompt_includes_issue_text() -> None:
    prompt = _build_coder_prompt("Fix the parser", {}, "/repo")
    assert "Fix the parser" in prompt


def test_build_coder_prompt_includes_repo_dir() -> None:
    prompt = _build_coder_prompt("issue", {}, "/home/user/repo")
    assert "/home/user/repo" in prompt


def test_build_coder_prompt_includes_plan_steps() -> None:
    plan = {
        "steps": [{"file_path": "foo.py", "action": "modify", "description": "Add bar"}],
        "rationale": "Because",
    }
    prompt = _build_coder_prompt("issue", plan, "/repo")
    assert "foo.py" in prompt
    assert "Add bar" in prompt
    assert "Because" in prompt


# ---------------------------------------------------------------------------
# _parse_diff unit tests (pure, no I/O)
# ---------------------------------------------------------------------------


def test_parse_diff_splits_by_file() -> None:
    raw = (
        "diff --git a/foo.py b/foo.py\n"
        "index abc..def 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,1 +1,2 @@\n"
        " existing\n"
        "+added\n"
        "diff --git a/bar.py b/bar.py\n"
        "index 111..222 100644\n"
        "--- a/bar.py\n"
        "+++ b/bar.py\n"
        "@@ -1,1 +1,2 @@\n"
        " x\n"
        "+y\n"
    )
    diffs = _parse_diff(raw)
    assert len(diffs) == 2
    assert diffs[0]["file_path"] == "foo.py"
    assert "added" in diffs[0]["patch"]
    assert diffs[1]["file_path"] == "bar.py"


def test_parse_diff_empty_input_returns_empty() -> None:
    assert _parse_diff("") == []
    assert _parse_diff("   \n  ") == []


def test_parse_diff_single_file() -> None:
    raw = (
        "diff --git a/src/init.py b/src/init.py\n"
        "index 000..111 100644\n"
        "--- a/src/init.py\n"
        "+++ b/src/init.py\n"
        "@@ -1 +1,2 @@\n"
        " pass\n"
        "+# comment\n"
    )
    diffs = _parse_diff(raw)
    assert len(diffs) == 1
    assert diffs[0]["file_path"] == "src/init.py"


# ---------------------------------------------------------------------------
# execute_tool unit tests (mocked sandbox)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_read_file() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="def foo(): pass\n")

    result = await execute_tool(sandbox, "read_file", {"path": "/repo/foo.py"})

    assert result == {"content": "def foo(): pass\n"}
    sandbox.files.read.assert_awaited_once_with("/repo/foo.py")


@pytest.mark.asyncio
async def test_execute_tool_read_file_error_returns_error_dict() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(side_effect=FileNotFoundError("not found"))

    result = await execute_tool(sandbox, "read_file", {"path": "/missing.py"})

    assert "error" in result
    assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_execute_tool_write_file() -> None:
    sandbox = AsyncMock()
    sandbox.files.write = AsyncMock(return_value=MagicMock())
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0))

    result = await execute_tool(
        sandbox, "write_file", {"path": "/repo/new.py", "content": "print('hi')\n"}
    )

    assert result == {"success": True}
    sandbox.files.write.assert_awaited_once_with("/repo/new.py", "print('hi')\n")


@pytest.mark.asyncio
async def test_execute_tool_list_files() -> None:
    from e2b.sandbox.filesystem.filesystem import EntryInfo, FileType

    entry = MagicMock(spec=EntryInfo)
    entry.name = "foo.py"
    entry.type = FileType.FILE

    sandbox = AsyncMock()
    sandbox.files.list = AsyncMock(return_value=[entry])

    result = await execute_tool(sandbox, "list_files", {"directory": "/repo"})

    assert "entries" in result
    assert len(result["entries"]) == 1
    assert result["entries"][0]["name"] == "foo.py"


@pytest.mark.asyncio
async def test_execute_tool_unknown_returns_error() -> None:
    sandbox = AsyncMock()
    result = await execute_tool(sandbox, "nonexistent_tool", {})
    assert "error" in result
    assert "Unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# coder_node integration tests (mocked sandbox + Gemini + real test DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coder_executes_tool_calls(coder_run: Run, session_factory) -> None:
    """coder_node executes a tool call sequence and returns diffs."""
    sandbox = _make_sandbox_mock()
    sandbox.files.read = AsyncMock(return_value="def old(): pass\n")

    # Sequence: read_file → write_file → done (text only)
    client_mock = _make_client_mock(
        _make_fn_call_response("read_file", {"path": "/home/user/repo/hello.py"}),
        _make_fn_call_response(
            "write_file",
            {"path": "/home/user/repo/hello.py", "content": "def hello(): pass\n"},
        ),
        _make_text_response("All done."),
    )

    # Simulate a non-empty git diff for the write_file step
    from e2b import CommandResult

    def _run_side_effect(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        result = MagicMock(spec=CommandResult)
        result.error = None
        if cmd.strip().endswith(" diff"):
            result.stdout = (
                "diff --git a/hello.py b/hello.py\n"
                "index 000..111 100644\n"
                "--- a/hello.py\n"
                "+++ b/hello.py\n"
                "@@ -1 +1,2 @@\n"
                " def old(): pass\n"
                "+def hello(): pass\n"
            )
            result.stderr = ""
            result.exit_code = 0
        else:
            result.stdout = ""
            result.stderr = ""
            result.exit_code = 0
        return result

    sandbox.commands.run = AsyncMock(side_effect=_run_side_effect)

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        result = await coder_node(_base_state(coder_run))

    assert result["current_agent"] == "coder"
    assert isinstance(result["diffs"], list)
    assert len(result["diffs"]) == 1
    assert result["diffs"][0]["file_path"] == "hello.py"
    sandbox.kill.assert_awaited_once()


@pytest.mark.asyncio
async def test_coder_bounded_by_max_iterations(coder_run: Run, session_factory) -> None:
    """When the model keeps calling tools, the loop stops after MAX_CODER_TOOL_ITERATIONS."""
    sandbox = _make_sandbox_mock()

    # Model always returns a tool call — never stops on its own.
    infinite_fn_call = _make_fn_call_response("read_file", {"path": "/repo/x.py"})
    client_mock = _make_client_mock(*([infinite_fn_call] * 20))

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
        patch("app.agents.coder.settings.MAX_CODER_TOOL_ITERATIONS", 3),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        result = await coder_node(_base_state(coder_run))

    # Should complete (not raise), with exactly 3 generate_content calls.
    assert result["current_agent"] == "coder"
    assert client_mock.aio.models.generate_content.await_count == 3
    sandbox.kill.assert_awaited_once()


@pytest.mark.asyncio
async def test_coder_persists_diffs_to_db(
    coder_run: Run, session_factory, db
) -> None:
    """After coder_node succeeds, Diff rows exist in the DB with correct fields."""
    sandbox = _make_sandbox_mock()

    from e2b import CommandResult

    def _run_side_effect(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        r = MagicMock(spec=CommandResult)
        r.error = None
        if cmd.strip().endswith(" diff"):
            r.stdout = (
                "diff --git a/src/lib.py b/src/lib.py\n"
                "index aaa..bbb 100644\n"
                "--- a/src/lib.py\n"
                "+++ b/src/lib.py\n"
                "@@ -3,0 +4,1 @@\n"
                "+def hello(): return 'hi'\n"
            )
        else:
            r.stdout = ""
        r.stderr = ""
        r.exit_code = 0
        return r

    sandbox.commands.run = AsyncMock(side_effect=_run_side_effect)

    client_mock = _make_client_mock(_make_text_response("Done."))

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        await coder_node(_base_state(coder_run))

    diffs = (
        (await db.execute(select(Diff).where(Diff.run_id == coder_run.id)))
        .scalars()
        .all()
    )

    assert len(diffs) == 1
    assert diffs[0].file_path == "src/lib.py"
    assert "+def hello(): return 'hi'" in diffs[0].patch
    assert diffs[0].approved is False
    assert diffs[0].run_id == coder_run.id


@pytest.mark.asyncio
async def test_coder_logs_agent_step(
    coder_run: Run, session_factory, db
) -> None:
    """After coder_node runs, an AgentStep row with agent=coder exists."""
    sandbox = _make_sandbox_mock()
    client_mock = _make_client_mock(_make_text_response("Done."))

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        await coder_node(_base_state(coder_run))

    steps = (
        (
            await db.execute(
                select(AgentStep).where(
                    AgentStep.run_id == coder_run.id,
                    AgentStep.agent == AgentRole.coder,
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(steps) == 1
    step = steps[0]
    assert step.step_index == 1
    assert step.agent == AgentRole.coder
    assert "clone_url" in step.input
    assert "diff_count" in step.output


@pytest.mark.asyncio
async def test_coder_sandbox_killed_on_clone_failure(
    coder_run: Run, session_factory
) -> None:
    """sandbox.kill() is called in the finally block even when git clone fails."""
    sandbox = _make_sandbox_mock()

    from e2b import CommandResult

    def _failing_clone(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        r = MagicMock(spec=CommandResult)
        r.stdout = ""
        r.stderr = "fatal: repository not found"
        r.exit_code = 128
        r.error = None
        return r

    sandbox.commands.run = AsyncMock(side_effect=_failing_clone)
    client_mock = MagicMock()

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        with pytest.raises(RuntimeError, match="git clone failed"):
            await coder_node(_base_state(coder_run))

    # Kill must have been called despite the error.
    sandbox.kill.assert_awaited_once()


@pytest.mark.asyncio
async def test_coder_sets_run_status_to_coding(
    coder_run: Run, session_factory, db
) -> None:
    """coder_node transitions run.status to coding at the start of execution."""
    sandbox = _make_sandbox_mock()
    # Fail after setting status so we can catch the status update.
    from e2b import CommandResult

    def _fail(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        r = MagicMock(spec=CommandResult)
        r.stdout = ""
        r.stderr = "error"
        r.exit_code = 1
        r.error = None
        return r

    sandbox.commands.run = AsyncMock(side_effect=_fail)
    client_mock = MagicMock()

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        with pytest.raises(RuntimeError):
            await coder_node(_base_state(coder_run))

    await db.refresh(coder_run)
    # Status was set to coding before the clone attempt.
    assert coder_run.status == RunStatus.coding


@pytest.mark.asyncio
async def test_coder_no_changes_produces_empty_diffs(
    coder_run: Run, session_factory, db
) -> None:
    """When git diff returns nothing, diffs list is empty and no Diff rows are written."""
    sandbox = _make_sandbox_mock()  # default: commands.run returns empty stdout
    client_mock = _make_client_mock(_make_text_response("Nothing to change."))

    with (
        patch("app.agents.coder.AsyncSandbox") as mock_sb_cls,
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        mock_sb_cls.create = AsyncMock(return_value=sandbox)
        result = await coder_node(_base_state(coder_run))

    assert result["diffs"] == []

    diff_count = len(
        (await db.execute(select(Diff).where(Diff.run_id == coder_run.id)))
        .scalars()
        .all()
    )
    assert diff_count == 0
