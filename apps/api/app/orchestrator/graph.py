"""LangGraph agent graph builder.

Currently wires a single Planner node.  Adding Coder/Tester/Reviewer in
Part 2 is a small extension: call ``builder.add_node`` + ``builder.add_edge``
and update the status-transition logic in ``execute_run`` — no existing node
or schema needs to change.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.planner import planner_node
from app.agents.state import AgentState


def build_graph() -> Any:
    """Build and compile the Foreman agent graph.

    Returns a compiled ``CompiledStateGraph`` that accepts an ``AgentState``
    dict via ``.ainvoke(state)``.  The graph is stateless between invocations
    — creating a new instance per run is intentional and cheap.
    """
    builder: StateGraph = StateGraph(AgentState)

    # --- Nodes (Part 1: Planner only) --------------------------------------
    builder.add_node("planner", planner_node)

    # --- Edges -------------------------------------------------------------
    builder.set_entry_point("planner")
    builder.add_edge("planner", END)

    return builder.compile()
