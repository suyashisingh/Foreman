"""LangGraph agent graph builder.

Current graph:

    Planner → Coder → Tester
                      ↓ test_passed=True           → END (awaiting_approval)
                      ↓ test_passed=False, retries → Coder  (retry loop)
                      ↓ test_passed=False, exhausted → END (failed)

The sandbox is created once in ``execute_run`` (tasks.py), threaded through
``AgentState``, and killed in ``execute_run``'s ``finally`` block.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.coder import coder_node
from app.agents.planner import planner_node
from app.agents.state import AgentState
from app.agents.tester import tester_node
from app.core.config import settings


def _route_after_tester(state: AgentState) -> str:
    """Routing function called after every Tester invocation.

    Returns one of three string keys:
    - ``"pass"``      → graph ends; tasks.py sets status to awaiting_approval.
    - ``"retry"``     → graph loops back to the Coder with test failure context.
    - ``"exhausted"`` → graph ends; tasks.py sets status to failed.
    """
    if state.get("test_passed"):
        return "pass"
    if (state.get("retry_count") or 0) < settings.MAX_CODER_RETRIES:
        return "retry"
    return "exhausted"


def build_graph() -> Any:
    """Build and compile the Foreman agent graph.

    Returns a compiled ``CompiledStateGraph`` that accepts an ``AgentState``
    dict via ``.ainvoke(state)``.  The graph is stateless between invocations
    — creating a new instance per run is intentional and cheap.
    """
    builder: StateGraph = StateGraph(AgentState)

    # --- Nodes -------------------------------------------------------------
    builder.add_node("planner", planner_node)
    builder.add_node("coder", coder_node)
    builder.add_node("tester", tester_node)

    # --- Edges -------------------------------------------------------------
    builder.set_entry_point("planner")
    builder.add_edge("planner", "coder")
    builder.add_edge("coder", "tester")
    builder.add_conditional_edges(
        "tester",
        _route_after_tester,
        {"pass": END, "retry": "coder", "exhausted": END},
    )

    return builder.compile()
