from typing import Optional

from .config import DEFAULT_GOAL_HINT, OUT_DIR
from .graph import build_graph
from .types import AgentAState


def run(goal: Optional[str] = None) -> AgentAState:
    goal_text = goal or DEFAULT_GOAL_HINT or "create a new project"

    app = build_graph()
    initial_state: AgentAState = {
        "goal": goal_text,
        "screenshot_path": None,
        "annotated_path": None,
        "elements": [],
        "top_elements": [],
        "chosen_id": None,
        "reason": None,
    }

    final_state = app.invoke(initial_state)
    return final_state


def print_summary(goal: str, final_state: AgentAState) -> None:
    print("\n=== Agent A result ===")
    print("Goal:", goal)
    print("Chosen id:", final_state["chosen_id"])
    print("Reason:", final_state["reason"])
    print("Annotated screenshot:", final_state["annotated_path"])
    print("Elements JSON:", OUT_DIR / "elements.json")

