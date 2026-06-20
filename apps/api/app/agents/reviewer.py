"""Reviewer LangGraph node: produce a structured code review before human approval.

This is the fourth node in the Foreman agent graph.  It runs after the Tester
confirms tests pass and before the graph ends.  It:

1. Transitions the run to ``reviewing`` status.
2. Builds a prompt from the issue text, implementation plan, and diffs.
3. Calls Gemini with ``response_schema=ReviewOutput`` to produce a structured review.
4. Persists an ``AgentStep`` row for telemetry.
5. Returns the review dict in state so ``GET /runs/{id}`` can surface it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel

from app.agents.llm_client import get_llm_client
from app.agents.state import AgentState
from app.db import session as _db_session
from app.db.models import AgentRole, Run, RunStatus
from app.orchestrator.logging import log_agent_step

logger = logging.getLogger(__name__)


class ReviewOutput(BaseModel):
    """Structured review produced by the Reviewer node."""

    summary: str
    risk_level: str  # "low" | "medium" | "high"
    risk_notes: str
    pr_title: str
    pr_description: str


def _build_reviewer_prompt(
    issue_text: str,
    plan: dict[str, Any],
    diffs: list[dict[str, Any]],
) -> str:
    """Build the Reviewer LLM prompt from issue, plan, and diffs."""
    steps = plan.get("steps", [])
    steps_text = (
        "\n".join(
            f"  - {s.get('action', '?').upper()} {s.get('file_path', '?')}: "
            f"{s.get('description', '')}"
            for s in steps
        )
        or "  (none)"
    )

    diffs_text = ""
    for d in diffs:
        diffs_text += (
            f"\n### {d.get('file_path', 'unknown')}\n"
            f"```diff\n{d.get('patch', '')}\n```\n"
        )
    if not diffs_text:
        diffs_text = "(no diffs)"

    return (
        "You are a senior engineer reviewing an AI-generated code change"
        " for correctness and safety.\n\n"
        f"## Issue\n{issue_text}\n\n"
        f"## Implementation Plan\n{steps_text}\n\n"
        f"## Diffs Applied\n{diffs_text}\n\n"
        "## Instructions\n"
        "Review the changes above and produce a structured assessment:\n"
        "- summary: 2-4 sentences on what changed and whether it looks correct.\n"
        '- risk_level: One of "low", "medium", or "high" (regression risk).\n'
        "- risk_notes: Specific risks or edge cases."
        ' Use "None identified." if risk_level is low.\n'
        "- pr_title: Short imperative PR title (50 chars max).\n"
        "- pr_description: Markdown PR description (3-8 bullet points).\n\n"
        "Respond with a JSON object matching the schema exactly. Be concise.\n"
    )


async def reviewer_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: review the agent's changes and produce structured output.

    Reads ``run_id``, ``issue_text``, ``plan``, ``diffs``, and ``retry_count``
    from *state*.

    Side effects committed to the DB:
    - ``Run.status`` → ``reviewing`` at start.
    - ``AgentStep`` row for telemetry with the review output.

    Returns:
        Partial ``AgentState`` with ``review`` and ``current_agent`` updated.
    """
    run_id: uuid.UUID = state["run_id"]
    retry_count: int = state.get("retry_count") or 0
    step_index = 3 + 2 * retry_count

    if _db_session.async_session_factory is None:
        raise RuntimeError("DB session factory not initialised in reviewer_node")

    async with _db_session.async_session_factory() as db:
        run: Run | None = await db.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} not found in reviewer_node")
        run.status = RunStatus.reviewing
        await db.commit()

    issue_text = state["issue_text"]
    plan = state.get("plan") or {}
    diffs = state.get("diffs") or []

    prompt = _build_reviewer_prompt(issue_text, plan, diffs)

    llm = get_llm_client()
    llm_response = await llm.generate_structured(prompt, ReviewOutput)
    review_dict = llm_response.result.model_dump()

    async with _db_session.async_session_factory() as db:
        await log_agent_step(
            db=db,
            run_id=run_id,
            agent=AgentRole.reviewer,
            step_index=step_index,
            input_data={
                "issue_text": issue_text,
                "plan_steps": len(plan.get("steps", [])),
                "diff_count": len(diffs),
            },
            output_data=review_dict,
            tool_calls=[],
            token_usage={
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
            },
            latency_ms=llm_response.latency_ms,
        )

    logger.info(
        "Reviewer done",
        extra={"run_id": str(run_id), "risk_level": review_dict.get("risk_level")},
    )
    return {"current_agent": "reviewer", "review": review_dict}
