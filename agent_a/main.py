from typing import List, Optional

from .config import OUT_DIR
from .graph import build_graph
from .types import AgentAState
from langsmith import uuid7
from dotenv import load_dotenv
load_dotenv()


def run(user_query: Optional[str] = None, history: Optional[List[str]] = None) -> AgentAState:
    query = user_query or "create a new issue"

    app = build_graph()
    print(f"[AgentA] Starting run with user query: {query}")
    initial_state: AgentAState = {
        "user_query": query,
        "history": history or [],
        "screenshot_path": None,
        "elements": [],
        "instruction": None,
        "tried_ids": [],
        "top_elements": [],
    }

    run_id = uuid7()
    
    # Add a run label to make traces easier to read
    final_state = app.invoke(initial_state, config={"run_id": run_id, "run_name": "agent_a_pipeline"})
    print("[AgentA] Run completed")
    return final_state


def print_summary(user_query: str, final_state: AgentAState) -> None:
    print("\n=== Agent A result ===")
    print("User query:", user_query)
    print("Instruction:", final_state.get("instruction"))
    print("Screenshot:", final_state.get("screenshot_path"))
    print("Elements JSON:", OUT_DIR / "elements.json")
    top = final_state.get("top_elements") or []
    if top:
        print("Top candidates (id, role, name, score):")
        for e in top:
            try:
                score_val = float(e.get("score", 0.0))
            except Exception:
                score_val = 0.0
            print(f"  - {e.get('id')} | {e.get('role')} | {e.get('name')} | score={score_val:.2f}")
