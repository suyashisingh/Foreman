"""Unit tests for the Coder LangGraph node (coder.py) and tool executor (tools.py).

The e2b sandbox and Gemini API are fully mocked — no live services required.
Tests cover:
- The tool-use loop (tool calls executed, results fed back).
- The MAX_CODER_TOOL_ITERATIONS bound (loop exits gracefully when hit).
- Per-file diff persistence to the ``diffs`` table.
- Sandbox NOT killed in coder_node (sandbox lifecycle is tasks.py's job).
- Each tool function (read_file, write_file, list_files) in isolation.
- Retry behaviour: prompt includes test failure, git clone skipped, diffs replaced.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.coder import _build_coder_prompt, _parse_diff, coder_node
from app.agents.state import AgentState
from app.agents.tools import execute_tool
from app.db.models import (
    AgentRole,
    AgentStep,
    Diff,
    Repo,
    RepoStatus,
    Run,
    RunStatus,
    User,
)

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
    """Build a mock genai.Client; ``generate_content`` iterates through *responses*."""
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


def _base_state(run: Run, sandbox: Any = None, **overrides: Any) -> AgentState:
    """Build a minimal AgentState for coder tests.

    The sandbox mock is passed in (not created inside coder_node anymore).
    """
    sb = sandbox if sandbox is not None else AsyncMock()
    base: AgentState = AgentState(
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
        sandbox=sb,
        test_passed=None,
        test_output=None,
    )
    base.update(overrides)  # type: ignore[attr-defined]
    return base


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
        "steps": [
            {"file_path": "foo.py", "action": "modify", "description": "Add bar"}
        ],
        "rationale": "Because",
    }
    prompt = _build_coder_prompt("issue", plan, "/repo")
    assert "foo.py" in prompt
    assert "Add bar" in prompt
    assert "Because" in prompt


def test_build_coder_prompt_no_retry_section_when_no_test_output() -> None:
    prompt = _build_coder_prompt("Fix it", {}, "/repo", test_output=None)
    assert "Previous Attempt Failed" not in prompt


def test_build_coder_prompt_retry_section_present_when_test_output_set() -> None:
    prompt = _build_coder_prompt(
        "Fix it", {}, "/repo", test_output="FAILED test_foo.py::test_bar"
    )
    assert "Previous Attempt Failed" in prompt
    assert "FAILED test_foo.py::test_bar" in prompt


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
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        result = await coder_node(_base_state(coder_run, sandbox=sandbox))

    assert result["current_agent"] == "coder"
    assert isinstance(result["diffs"], list)
    assert len(result["diffs"]) == 1
    assert result["diffs"][0]["file_path"] == "hello.py"
    # Sandbox is NOT killed here — that is tasks.py's responsibility.
    sandbox.kill.assert_not_awaited()


@pytest.mark.asyncio
async def test_coder_bounded_by_max_iterations(coder_run: Run, session_factory) -> None:
    """Tool-use loop exits after MAX_CODER_TOOL_ITERATIONS when model never stops."""
    sandbox = _make_sandbox_mock()

    # Model always returns a tool call — never stops on its own.
    infinite_fn_call = _make_fn_call_response("read_file", {"path": "/repo/x.py"})
    client_mock = _make_client_mock(*([infinite_fn_call] * 20))

    with (
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
        patch("app.agents.coder.settings.MAX_CODER_TOOL_ITERATIONS", 3),
    ):
        result = await coder_node(_base_state(coder_run, sandbox=sandbox))

    assert result["current_agent"] == "coder"
    assert client_mock.aio.models.generate_content.await_count == 3
    sandbox.kill.assert_not_awaited()


@pytest.mark.asyncio
async def test_coder_persists_diffs_to_db(coder_run: Run, session_factory, db) -> None:
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
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        await coder_node(_base_state(coder_run, sandbox=sandbox))

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
async def test_coder_logs_agent_step(coder_run: Run, session_factory, db) -> None:
    """After coder_node runs, an AgentStep row with agent=coder exists."""
    sandbox = _make_sandbox_mock()
    client_mock = _make_client_mock(_make_text_response("Done."))

    with (
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        await coder_node(_base_state(coder_run, sandbox=sandbox))

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
async def test_coder_clone_failure_raises_without_sandbox_kill(
    coder_run: Run, session_factory
) -> None:
    """git clone failure raises RuntimeError; sandbox.kill is NOT called here."""
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
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        with pytest.raises(RuntimeError, match="git clone failed"):
            await coder_node(_base_state(coder_run, sandbox=sandbox))

    # Sandbox lifecycle is tasks.py's responsibility — never killed in coder_node.
    sandbox.kill.assert_not_awaited()


@pytest.mark.asyncio
async def test_coder_sets_run_status_to_coding(
    coder_run: Run, session_factory, db
) -> None:
    """coder_node transitions run.status to coding at the start of execution."""
    sandbox = _make_sandbox_mock()
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
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        with pytest.raises(RuntimeError):
            await coder_node(_base_state(coder_run, sandbox=sandbox))

    await db.refresh(coder_run)
    assert coder_run.status == RunStatus.coding


@pytest.mark.asyncio
async def test_coder_no_changes_produces_empty_diffs(
    coder_run: Run, session_factory, db
) -> None:
    """Empty git diff produces empty diffs list and no Diff rows in the DB."""
    sandbox = _make_sandbox_mock()
    client_mock = _make_client_mock(_make_text_response("Nothing to change."))

    with (
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        result = await coder_node(_base_state(coder_run, sandbox=sandbox))

    assert result["diffs"] == []

    diff_count = len(
        (await db.execute(select(Diff).where(Diff.run_id == coder_run.id)))
        .scalars()
        .all()
    )
    assert diff_count == 0


# ---------------------------------------------------------------------------
# Retry-specific tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coder_retry_skips_git_clone(coder_run: Run, session_factory) -> None:
    """On retry (test_output set), coder_node does NOT run git clone."""
    sandbox = _make_sandbox_mock()
    client_mock = _make_client_mock(_make_text_response("Fixed."))
    clone_calls: list[str] = []

    from e2b import CommandResult

    def _run_side_effect(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        r = MagicMock(spec=CommandResult)
        r.stdout = ""
        r.stderr = ""
        r.exit_code = 0
        r.error = None
        if "git clone" in cmd:
            clone_calls.append(cmd)
        return r

    sandbox.commands.run = AsyncMock(side_effect=_run_side_effect)

    with (
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        await coder_node(
            _base_state(
                coder_run,
                sandbox=sandbox,
                retry_count=0,
                test_output="FAILED test_foo.py::test_bar\n1 failed",
            )
        )

    assert clone_calls == [], "git clone must not run on retry"


@pytest.mark.asyncio
async def test_coder_retry_prompt_contains_test_output(
    coder_run: Run, session_factory
) -> None:
    """On retry, the prompt sent to Gemini contains the previous test failure."""
    sandbox = _make_sandbox_mock()
    captured_prompts: list[str] = []

    def _capture_content(model: str, contents: Any, config: Any = None) -> MagicMock:
        # contents[0] is the user message; extract text from its first part.
        try:
            captured_prompts.append(contents[0].parts[0].text)
        except Exception:
            pass
        return _make_text_response("ok")

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=_capture_content)

    with (
        patch("app.agents.coder.genai.Client", return_value=client),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        await coder_node(
            _base_state(
                coder_run,
                sandbox=sandbox,
                retry_count=0,
                test_output="AssertionError: 1 != 2",
            )
        )

    assert captured_prompts, "generate_content was never called"
    assert "Previous Attempt Failed" in captured_prompts[0]
    assert "AssertionError: 1 != 2" in captured_prompts[0]


@pytest.mark.asyncio
async def test_coder_increments_retry_count(coder_run: Run, session_factory) -> None:
    """retry_count in the returned state is incremented by 1 on each retry."""
    sandbox = _make_sandbox_mock()
    # Use return_value (not side_effect list) so the same response repeats.
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=_make_text_response("Done.")
    )

    with (
        patch("app.agents.coder.genai.Client", return_value=client),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        # First invocation — not a retry
        result_first = await coder_node(
            _base_state(coder_run, sandbox=sandbox, retry_count=0, test_output=None)
        )
        assert result_first["retry_count"] == 0

        # Second invocation — first retry
        result_retry = await coder_node(
            _base_state(
                coder_run,
                sandbox=sandbox,
                retry_count=0,
                test_output="1 failed",
            )
        )
        assert result_retry["retry_count"] == 1


@pytest.mark.asyncio
async def test_coder_retry_replaces_old_diffs(
    coder_run: Run, session_factory, db
) -> None:
    """On retry, prior-attempt Diff rows are deleted before new ones are inserted."""
    sandbox = _make_sandbox_mock()
    client_mock = _make_client_mock(_make_text_response("Done."))

    # Seed an existing Diff row to simulate a prior attempt.
    from app.db.models import Diff as DiffModel

    async with session_factory() as seed_db:
        seed_db.add(
            DiffModel(
                run_id=coder_run.id,
                file_path="old_file.py",
                patch="--- a/old\n+++ b/old\n",
                approved=False,
            )
        )
        await seed_db.commit()

    from e2b import CommandResult

    def _run_side_effect(cmd: str, timeout: float | None = None, **kwargs: Any) -> Any:
        r = MagicMock(spec=CommandResult)
        r.error = None
        if cmd.strip().endswith(" diff"):
            r.stdout = (
                "diff --git a/new_file.py b/new_file.py\n"
                "index 000..111 100644\n"
                "--- a/new_file.py\n"
                "+++ b/new_file.py\n"
                "@@ -1 +1,2 @@\n"
                " pass\n"
                "+# fix\n"
            )
        else:
            r.stdout = ""
        r.stderr = ""
        r.exit_code = 0
        return r

    sandbox.commands.run = AsyncMock(side_effect=_run_side_effect)

    with (
        patch("app.agents.coder.genai.Client", return_value=client_mock),
        patch("app.agents.coder._db_session.async_session_factory", session_factory),
    ):
        await coder_node(
            _base_state(
                coder_run,
                sandbox=sandbox,
                retry_count=0,
                test_output="1 failed",
            )
        )

    diffs = (
        (await db.execute(select(Diff).where(Diff.run_id == coder_run.id)))
        .scalars()
        .all()
    )

    # old_file.py must be gone; only new_file.py remains.
    file_paths = [d.file_path for d in diffs]
    assert "old_file.py" not in file_paths
    assert "new_file.py" in file_paths
