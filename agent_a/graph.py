from langgraph.graph import END, StateGraph

from .agent import agent_a
from .types import AgentAState
from .workflow import capture_ui


def build_graph():
    graph = StateGraph(AgentAState)
    graph.add_node("capture_ui", capture_ui)
    graph.add_node("agent_a", agent_a)

    graph.set_entry_point("capture_ui")
    graph.add_edge("capture_ui", "agent_a")
    graph.add_edge("agent_a", END)

    return graph.compile()

