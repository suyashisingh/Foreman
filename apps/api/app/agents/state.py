"""LangGraph state schema for the Foreman agent graph.

TypedDict is used (rather than Pydantic BaseModel) because LangGraph's
StateGraph uses TypedDict fields as the canonical node I/O contract and
natively supports Annotated reducers (e.g. ``operator.add`` for appending
list fields) that don't map cleanly onto Pydantic's model_validator
approach.  Pydantic IS still used for structured LLM output (Plan,
PlanStep in planner.py) — just not for the graph state itself.
"""

from __future__ import annotations

import uuid
from typing import Any, TypedDict


class _AgentStateRequired(TypedDict):
    """Required keys — always present when the graph is invoked."""

    run_id: uuid.UUID
    repo_id: uuid.UUID
    issue_text: str


class AgentState(_AgentStateRequired, total=False):
    """Shared state flowing between every node in the agent graph.

    Inherits required keys (``run_id``, ``repo_id``, ``issue_text``) from
    ``_AgentStateRequired``.  The remaining keys are optional (``total=False``)
    — nodes return only the keys they update, and LangGraph merges them into
    the running state dict.

    Fields
    ------
    retrieved_context
        Code chunks returned by ``search_repo_chunks``; populated by the
        Planner node before the LLM call so the prompt includes real context.
    plan
        Serialised ``Plan`` dict produced by the Planner; ``None`` until
        planning completes.
    current_agent
        Name of the node that most recently updated state (e.g. "planner").
    retry_count
        Number of completed Coder retry iterations.  Incremented at the start
        of each non-first Coder invocation; checked by the post-Tester routing
        function to decide whether to retry or exhaust.
    error
        Human-readable error message if any node has failed; ``None`` otherwise.
    sandbox
        Live ``e2b.AsyncSandbox`` handle, created once in ``execute_run`` and
        shared across all Coder and Tester invocations in the retry loop.
    test_passed
        ``True`` if the last Tester run exited 0; ``False`` otherwise; ``None``
        before the first Tester invocation.
    test_output
        Combined stdout + stderr from the last ``pytest`` run; fed back into
        the Coder prompt on retry so the model knows what to fix.
    """

    retrieved_context: list[dict[str, Any]]
    plan: dict[str, Any] | None
    # Per-file diffs produced by the Coder node. Each entry has "file_path"
    # and "patch" (unified diff section for that file).  Populated after the
    # Coder's tool-use loop completes and `git diff` is captured.
    diffs: list[dict[str, Any]]
    current_agent: str
    retry_count: int
    error: str | None
    # --- Sandbox and test state (Day 4) ------------------------------------
    # Live e2b AsyncSandbox handle shared across the Coder↔Tester loop.
    # Created once in execute_run (tasks.py) and killed in its finally block.
    # Typed as Any because this object is only ever held in memory and never
    # serialised — the TypedDict contract is for node I/O, not persistence.
    sandbox: Any
    # Result of the most recent Tester node execution.
    test_passed: bool | None
    # Combined stdout + stderr from the most recent `pytest` run; used to
    # build the retry-feedback prompt when the Coder runs again.
    test_output: str | None
