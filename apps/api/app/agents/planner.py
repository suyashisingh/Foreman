"""Planner node: retrieve relevant code context and produce a structured plan.

This is the first node in the Foreman agent graph.  It:
1. Calls ``search_repo_chunks`` (via pgvector cosine search) to find the code
   chunks most relevant to the issue, giving the LLM real context.
2. Builds a prompt combining the issue text and the retrieved chunks.
3. Calls the configured LLM (via ``get_llm_client()``) for structured JSON
   output conforming to the ``Plan`` schema.
4. Logs the step (input, output, token usage, latency) via ``log_agent_step``.
5. Returns an updated ``AgentState`` with ``retrieved_context`` and ``plan``.
"""

import logging
import uuid
from typing import Any

from pydantic import BaseModel

from app.agents.llm_client import get_llm_client
from app.agents.state import AgentState
from app.db import session as _db_session
from app.db.models import AgentRole
from app.orchestrator.logging import log_agent_step
from app.retrieval.search import search_repo_chunks

logger = logging.getLogger(__name__)

# Number of code chunks to retrieve for the planner's context window.
_PLANNER_TOP_K = 8


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    """One concrete change in the implementation plan."""

    file_path: str
    action: str  # "create" | "modify" | "delete"
    description: str


class Plan(BaseModel):
    """Structured implementation plan produced by the Planner LLM call."""

    steps: list[PlanStep]
    rationale: str


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def _build_prompt(issue_text: str, chunks: list[dict[str, Any]]) -> str:
    """Assemble the planner prompt from the issue and retrieved code chunks."""
    chunk_text = (
        "\n\n".join(
            f"### {c.get('file_path', '')} — {c.get('symbol_name') or 'file'} "
            f"(similarity: {c.get('similarity', 0):.3f})\n{c.get('content', '')}"
            for c in chunks
        )
        or "(no relevant code found — repository may be empty)"
    )

    return f"""You are a software engineering planner for an autonomous coding agent.

Given the issue description and relevant code context below, produce a
structured implementation plan. Each step must identify a specific file and
describe exactly what change to make, referencing actual function/class names.

## Issue

{issue_text}

## Relevant Code Context

{chunk_text}

## Output Format

Return a JSON object with:
- steps: list of objects with file_path, action ("create"|"modify"|"delete"),
  and description (what specifically to change and why)
- rationale: a short paragraph explaining the overall approach

Be concrete. Reference real symbols from the context above.
"""


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


async def planner_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: retrieve context and produce a structured Plan.

    Reads ``run_id``, ``repo_id``, and ``issue_text`` from *state*.

    Returns a partial ``AgentState`` dict — LangGraph merges the returned
    keys into the running state, so only updated fields need to be returned.
    """
    run_id: uuid.UUID = state["run_id"]
    repo_id: uuid.UUID = state["repo_id"]
    issue_text: str = state["issue_text"]

    if _db_session.async_session_factory is None:
        raise RuntimeError("DB session factory not initialised in planner_node")

    async with _db_session.async_session_factory() as db:
        # --- Retrieve relevant code chunks via semantic search ---------------
        chunks = await search_repo_chunks(db, repo_id, issue_text, top_k=_PLANNER_TOP_K)
        context_dicts = [c.model_dump() for c in chunks]

        # --- Build prompt and call LLM --------------------------------------
        prompt = _build_prompt(issue_text, context_dicts)
        llm = get_llm_client()
        llm_response = await llm.generate_structured(prompt, Plan)
        plan_dict = llm_response.result.model_dump()

        # --- Persist agent step --------------------------------------------
        await log_agent_step(
            db=db,
            run_id=run_id,
            agent=AgentRole.planner,
            step_index=0,
            input_data={
                "issue_text": issue_text,
                "retrieved_chunk_count": len(context_dicts),
            },
            output_data=plan_dict,
            tool_calls=[],
            token_usage={
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
            },
            latency_ms=llm_response.latency_ms,
        )

    logger.info(
        "Planner node complete",
        extra={
            "run_id": str(run_id),
            "plan_steps": len(plan_dict.get("steps", [])),
            "input_tokens": llm_response.input_tokens,
            "output_tokens": llm_response.output_tokens,
            "latency_ms": llm_response.latency_ms,
        },
    )

    return {
        "retrieved_context": context_dicts,
        "plan": plan_dict,
        "current_agent": "planner",
    }
