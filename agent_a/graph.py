from langgraph.graph import END, StateGraph

from .agent import agent_a
from .agent_b import agent_b
from .executor import execute_plan
from .ranker import score_elements
from .types import AgentAState
from .workflow import capture_ui


from .history import finalize_step

def should_continue(state: AgentAState) -> str:
    if state.get("done"):
        return END
    return "capture_ui"

def build_graph():
    graph = StateGraph(AgentAState)
    graph.add_node("capture_ui", capture_ui)
    graph.add_node("agent_a", agent_a)
    graph.add_node("score_elements", score_elements)
    graph.add_node("agent_b", agent_b)
    graph.add_node("execute_plan", execute_plan)
    graph.add_node("finalize_step", finalize_step)

    graph.set_entry_point("capture_ui")
    graph.add_edge("capture_ui", "agent_a")
    graph.add_edge("agent_a", "score_elements")
    graph.add_edge("score_elements", "agent_b")
    graph.add_edge("agent_b", "execute_plan")
    graph.add_edge("execute_plan", "finalize_step")
    
    graph.add_conditional_edges(
        "finalize_step",
        should_continue,
        {END: END, "capture_ui": "capture_ui"}
    )

    return graph.compile()
