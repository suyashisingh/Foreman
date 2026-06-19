"""Unit tests for the Planner LangGraph node (planner.py).

The LLM client and search_repo_chunks are mocked so no real API calls or DB
reads are needed.  The ``test_planner_logs_agent_step`` test uses the real
test DB to verify the AgentStep row is actually persisted.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.llm_client import LLMError, LLMResponse
from app.agents.planner import Plan, PlanStep, _build_prompt, planner_node
from app.agents.state import AgentState
from app.db.models import AgentStep, Repo, RepoStatus, Run, RunStatus, User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pending_run(db):
    """A User+Repo+Run seeded directly in the test DB."""
    user = User(
        email="planner_test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Planner",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="test-repo",
        clone_url="https://github.com/example/repo.git",
        default_branch="main",
        status=RepoStatus.ready,
    )
    db.add(repo)
    await db.flush()

    run = Run(
        user_id=user.id,
        repo_id=repo.id,
        issue_text="Add a subtract method to Calculator",
        status=RunStatus.planning,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


def _mock_llm(steps=None, rationale="Test rationale"):
    """Return a mock LLM client that yields a valid Plan."""
    plan = Plan(
        steps=steps
        or [PlanStep(file_path="calc.py", action="modify", description="Add method")],
        rationale=rationale,
    )
    mock = MagicMock()
    mock.generate_structured = AsyncMock(
        return_value=LLMResponse(
            result=plan, input_tokens=50, output_tokens=30, latency_ms=400
        )
    )
    return mock


def _base_state(run: Run) -> AgentState:
    return AgentState(
        run_id=run.id,
        repo_id=run.repo_id,
        issue_text=run.issue_text,
        retrieved_context=[],
        plan=None,
        current_agent="",
        retry_count=0,
        error=None,
    )


# ---------------------------------------------------------------------------
# _build_prompt unit tests (pure, no I/O)
# ---------------------------------------------------------------------------


def test_build_prompt_includes_issue_text():
    prompt = _build_prompt("Fix the parser", [])
    assert "Fix the parser" in prompt


def test_build_prompt_includes_chunk_content():
    chunks = [
        {
            "file_path": "parser.py",
            "symbol_name": "parse",
            "similarity": 0.9,
            "content": "def parse(): pass",
        }
    ]
    prompt = _build_prompt("Fix it", chunks)
    assert "parser.py" in prompt
    assert "def parse(): pass" in prompt


def test_build_prompt_handles_no_chunks():
    prompt = _build_prompt("Do something", [])
    assert "no relevant code found" in prompt.lower()


# ---------------------------------------------------------------------------
# planner_node integration tests (mocked LLM + mocked search)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_calls_llm_with_prompt(pending_run, session_factory):
    """planner_node calls generate_structured with the issue text in the prompt."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.planner.search_repo_chunks", new=AsyncMock(return_value=[])),
        patch("app.agents.planner.get_llm_client", return_value=mock_llm),
        patch("app.agents.planner._db_session.async_session_factory", session_factory),
    ):
        await planner_node(_base_state(pending_run))

    mock_llm.generate_structured.assert_called_once()
    call_args = mock_llm.generate_structured.call_args
    assert pending_run.issue_text in call_args.args[0]
    assert call_args.args[1] is Plan


@pytest.mark.asyncio
async def test_planner_populates_plan_in_state(pending_run, session_factory):
    """planner_node returns state with plan populated from LLM response."""
    mock_llm = _mock_llm(
        steps=[
            PlanStep(file_path="calc.py", action="modify", description="Add subtract")
        ],
        rationale="Use subtraction operator",
    )

    with (
        patch("app.agents.planner.search_repo_chunks", new=AsyncMock(return_value=[])),
        patch("app.agents.planner.get_llm_client", return_value=mock_llm),
        patch("app.agents.planner._db_session.async_session_factory", session_factory),
    ):
        state = _base_state(pending_run)
        state["issue_text"] = "Add subtract"
        result = await planner_node(state)

    assert result["current_agent"] == "planner"
    assert result["plan"] is not None
    assert result["plan"]["rationale"] == "Use subtraction operator"
    steps = result["plan"]["steps"]
    assert len(steps) == 1
    assert steps[0]["file_path"] == "calc.py"


@pytest.mark.asyncio
async def test_planner_handles_llm_error(pending_run, session_factory):
    """If the LLM raises LLMError, planner_node propagates it."""
    mock_llm = MagicMock()
    mock_llm.generate_structured = AsyncMock(side_effect=LLMError("API down"))

    with (
        patch("app.agents.planner.search_repo_chunks", new=AsyncMock(return_value=[])),
        patch("app.agents.planner.get_llm_client", return_value=mock_llm),
        patch("app.agents.planner._db_session.async_session_factory", session_factory),
    ):
        with pytest.raises(LLMError, match="API down"):
            await planner_node(_base_state(pending_run))


@pytest.mark.asyncio
async def test_planner_logs_agent_step(pending_run, session_factory, db):
    """After planner_node runs, an AgentStep row exists in the DB."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.planner.search_repo_chunks", new=AsyncMock(return_value=[])),
        patch("app.agents.planner.get_llm_client", return_value=mock_llm),
        patch("app.agents.planner._db_session.async_session_factory", session_factory),
    ):
        await planner_node(_base_state(pending_run))

    steps = (
        (await db.execute(select(AgentStep).where(AgentStep.run_id == pending_run.id)))
        .scalars()
        .all()
    )

    assert len(steps) == 1
    step = steps[0]
    assert step.step_index == 0
    assert step.agent.value == "planner"
    assert step.latency_ms == 400
    assert step.token_usage["input_tokens"] == 50
    assert step.token_usage["output_tokens"] == 30
