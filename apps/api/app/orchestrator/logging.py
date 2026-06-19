"""Reusable helper for persisting agent step telemetry.

Every agent node (Planner now; Coder, Tester, Reviewer in Part 2) calls
``log_agent_step`` with its own input/output so the full execution trace is
recorded in ``agent_steps`` for auditing, debugging, and future fine-tuning.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRole, AgentStep

logger = logging.getLogger(__name__)


async def log_agent_step(
    db: AsyncSession,
    run_id: uuid.UUID,
    agent: AgentRole,
    step_index: int,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    token_usage: dict[str, Any],
    latency_ms: int,
) -> AgentStep:
    """Persist one ``AgentStep`` row and return it.

    Args:
        db:          Active async session — caller is responsible for keeping it
                     open until after this coroutine returns.
        run_id:      The run this step belongs to.
        agent:       Which agent role produced this step.
        step_index:  Zero-based position within the run (Planner=0, Coder=1 …).
        input_data:  Serialisable dict of what the node received as input.
        output_data: Serialisable dict of what the node produced as output.
        tool_calls:  List of tool-call records (empty for Planner; populated by
                     Coder when it writes files via e2b in Part 2).
        token_usage: Dict with at least ``input_tokens`` and ``output_tokens``.
        latency_ms:  Wall-clock time for the LLM call in milliseconds.

    Returns:
        The freshly committed ``AgentStep`` ORM instance.
    """
    step = AgentStep(
        run_id=run_id,
        agent=agent,
        step_index=step_index,
        input=input_data,
        output=output_data,
        tool_calls=tool_calls,
        token_usage=token_usage,
        latency_ms=latency_ms,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)

    logger.info(
        "Agent step logged",
        extra={
            "run_id": str(run_id),
            "agent": agent.value,
            "step_index": step_index,
            "latency_ms": latency_ms,
            "input_tokens": token_usage.get("input_tokens"),
            "output_tokens": token_usage.get("output_tokens"),
        },
    )
    return step
