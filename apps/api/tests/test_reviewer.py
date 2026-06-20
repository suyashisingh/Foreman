"""Unit tests for the Reviewer LangGraph node (reviewer.py).

The LLM client is mocked so no real API calls are made.  Tests cover:
- _build_reviewer_prompt content.
- reviewer_node sets run.status to reviewing.
- reviewer_node calls generate_structured with ReviewOutput.
- reviewer_node logs an AgentStep row with correct fields.
- step_index formula: 3 + 2*retry_count.
- review dict returned in state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.agents.llm_client import LLMResponse
from app.agents.reviewer import ReviewOutput, _build_reviewer_prompt, reviewer_node
from app.agents.state import AgentState
from app.db.models import AgentRole, AgentStep, Repo, RepoStatus, Run, RunStatus, User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def reviewer_run(db) -> Run:
    """A User+Repo+Run seeded for reviewer tests."""
    user = User(
        email="reviewer_test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$placeholder",
        name="Reviewer",
    )
    db.add(user)
    await db.flush()

    repo = Repo(
        user_id=user.id,
        name="review-repo",
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
        status=RunStatus.testing,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


def _mock_llm(review: ReviewOutput | None = None) -> MagicMock:
    if review is None:
        review = ReviewOutput(
            summary="Adds a subtract method correctly.",
            risk_level="low",
            risk_notes="None identified.",
            pr_title="feat: add subtract method",
            pr_description="- Adds `subtract(a, b)` to Calculator class",
        )
    mock = MagicMock()
    mock.generate_structured = AsyncMock(
        return_value=LLMResponse(
            result=review,
            input_tokens=80,
            output_tokens=40,
            latency_ms=600,
        )
    )
    return mock


def _reviewer_state(run: Run, retry_count: int = 0) -> AgentState:
    return AgentState(
        run_id=run.id,
        repo_id=run.repo_id,
        issue_text=run.issue_text,
        plan={
            "steps": [
                {
                    "file_path": "calc.py",
                    "action": "modify",
                    "description": "Add subtract method",
                }
            ],
            "rationale": "Simple arithmetic",
        },
        diffs=[
            {
                "file_path": "calc.py",
                "patch": (
                    "@@ -10,0 +11,3 @@\n"
                    "+    def subtract(a, b):\n"
                    "+        return a - b\n"
                ),
            }
        ],
        retry_count=retry_count,
    )


# ---------------------------------------------------------------------------
# _build_reviewer_prompt unit tests (pure, no I/O)
# ---------------------------------------------------------------------------


def test_build_reviewer_prompt_includes_issue_text() -> None:
    prompt = _build_reviewer_prompt("Fix the parser", {}, [])
    assert "Fix the parser" in prompt


def test_build_reviewer_prompt_includes_diff_content() -> None:
    diffs = [{"file_path": "foo.py", "patch": "+def new_func(): pass"}]
    prompt = _build_reviewer_prompt("Add func", {}, diffs)
    assert "foo.py" in prompt
    assert "+def new_func(): pass" in prompt


def test_build_reviewer_prompt_includes_plan_steps() -> None:
    plan = {
        "steps": [
            {"file_path": "calc.py", "action": "modify", "description": "Add subtract"}
        ]
    }
    prompt = _build_reviewer_prompt("Subtract", plan, [])
    assert "calc.py" in prompt
    assert "subtract" in prompt.lower()


def test_build_reviewer_prompt_handles_empty_diffs() -> None:
    prompt = _build_reviewer_prompt("Do something", {}, [])
    assert "no diffs" in prompt.lower()


def test_build_reviewer_prompt_handles_empty_plan() -> None:
    prompt = _build_reviewer_prompt("Fix it", {}, [])
    assert "none" in prompt.lower()


# ---------------------------------------------------------------------------
# reviewer_node integration tests (mocked LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reviewer_node_sets_run_status_to_reviewing(
    reviewer_run: Run, session_factory, db
) -> None:
    """reviewer_node sets run.status = reviewing before calling the LLM."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.reviewer.get_llm_client", return_value=mock_llm),
        patch("app.agents.reviewer._db_session.async_session_factory", session_factory),
    ):
        await reviewer_node(_reviewer_state(reviewer_run))

    await db.refresh(reviewer_run)
    assert reviewer_run.status == RunStatus.reviewing


@pytest.mark.asyncio
async def test_reviewer_node_calls_generate_structured(
    reviewer_run: Run, session_factory
) -> None:
    """reviewer_node calls generate_structured with ReviewOutput schema."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.reviewer.get_llm_client", return_value=mock_llm),
        patch("app.agents.reviewer._db_session.async_session_factory", session_factory),
    ):
        await reviewer_node(_reviewer_state(reviewer_run))

    mock_llm.generate_structured.assert_called_once()
    call_args = mock_llm.generate_structured.call_args
    assert call_args.args[1] is ReviewOutput
    assert reviewer_run.issue_text in call_args.args[0]


@pytest.mark.asyncio
async def test_reviewer_node_returns_review_in_state(
    reviewer_run: Run, session_factory
) -> None:
    """reviewer_node returns state with review dict and current_agent='reviewer'."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.reviewer.get_llm_client", return_value=mock_llm),
        patch("app.agents.reviewer._db_session.async_session_factory", session_factory),
    ):
        result = await reviewer_node(_reviewer_state(reviewer_run))

    assert result["current_agent"] == "reviewer"
    assert result["review"]["risk_level"] == "low"
    assert result["review"]["pr_title"] == "feat: add subtract method"


@pytest.mark.asyncio
async def test_reviewer_node_logs_agent_step(
    reviewer_run: Run, session_factory, db
) -> None:
    """reviewer_node persists an AgentStep with agent=reviewer."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.reviewer.get_llm_client", return_value=mock_llm),
        patch("app.agents.reviewer._db_session.async_session_factory", session_factory),
    ):
        await reviewer_node(_reviewer_state(reviewer_run, retry_count=0))

    steps = (
        (
            await db.execute(
                select(AgentStep).where(
                    AgentStep.run_id == reviewer_run.id,
                    AgentStep.agent == AgentRole.reviewer,
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(steps) == 1
    step = steps[0]
    assert step.agent == AgentRole.reviewer
    assert step.step_index == 3  # retry_count=0 → 3 + 2*0 = 3
    assert step.output["risk_level"] == "low"
    assert step.token_usage["input_tokens"] == 80
    assert step.latency_ms == 600


@pytest.mark.asyncio
async def test_reviewer_node_step_index_on_retry(
    reviewer_run: Run, session_factory, db
) -> None:
    """step_index = 3 + 2*retry_count; retry_count=1 → step_index=5."""
    mock_llm = _mock_llm()

    with (
        patch("app.agents.reviewer.get_llm_client", return_value=mock_llm),
        patch("app.agents.reviewer._db_session.async_session_factory", session_factory),
    ):
        await reviewer_node(_reviewer_state(reviewer_run, retry_count=1))

    steps = (
        (await db.execute(select(AgentStep).where(AgentStep.run_id == reviewer_run.id)))
        .scalars()
        .all()
    )

    assert len(steps) == 1
    assert steps[0].step_index == 5  # 3 + 2*1 = 5
