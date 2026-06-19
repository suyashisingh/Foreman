"""LangGraph agent graph builder.

Current graph: Planner → Coder → END.

Day 4 extension: add Tester and Reviewer nodes with ``add_node`` +
``add_edge`` calls below the existing edges — no existing node or schema
needs to change.
"""

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.coder import coder_node
from app.agents.planner import planner_node
from app.agents.state import AgentState


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

    # --- Edges -------------------------------------------------------------
    builder.set_entry_point("planner")
    builder.add_edge("planner", "coder")
    builder.add_edge("coder", END)

    return builder.compile()
