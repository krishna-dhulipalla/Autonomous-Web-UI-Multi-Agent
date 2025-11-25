from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from .config import OUT_DIR
from .graph import build_graph
from .types import AgentAState

load_dotenv()


def run(user_query: Optional[str] = None, history: Optional[List[str]] = None) -> AgentAState:
    query = user_query or "create a new issue"

    app = build_graph()
    print(f"[AgentA] Starting run with user query: {query}")
    run_id = str(uuid4())
    run_dir = OUT_DIR / f"run_{run_id}"
    # Initial state
    state: AgentAState = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "user_query": query,
        "history": history or [],
        "screenshot_path": None,
        "elements": [],
        "instruction": None,
        "plan_steps": None,
        "tried_ids": [],
        "top_elements": [],
        "actions": [],
        "followup_hint": None,
        "after_screenshot": None,
        "playwright": None,
        "context": None,
        "page": None,
        "step": 0,
        "done": False,
    }

    # Run the graph (it loops internally until done)
    final_state = app.invoke(
        state, config={"run_name": "agent_a_pipeline", "recursion_limit": 50})
    print("[AgentA] Run completed")

    # Cleanup
    if final_state.get("context"):
        final_state["context"].close()
    if final_state.get("playwright"):
        final_state["playwright"].stop()

    return final_state


def print_summary(user_query: str, final_state: AgentAState) -> None:
    print("\n=== Agent A result ===")
    print("User query:", user_query)
    print("Run dir:", final_state.get("run_dir"))
    print("Instruction:", final_state.get("instruction"))
    print("Screenshot:", final_state.get("screenshot_path"))
    step = max(final_state.get("step", 1) - 1, 0)
    print("Elements JSON:", Path(final_state.get("run_dir", "")) / f"elements_step_{step}.json")
    top = final_state.get("top_elements") or []
    if top:
        print("Top candidates (id, role, name, score):")
        for e in top:
            try:
                score_val = float(e.get("score", 0.0))
            except Exception:
                score_val = 0.0
            print(
                f"  - {e.get('id')} | {e.get('role')} | {e.get('name')} | score={score_val:.2f}")
    actions = final_state.get("actions") or []
    if actions:
        print("Actions:")
        for a in actions:
            print(f"  - {a}")
    if final_state.get("after_screenshot"):
        print("After-action screenshot:", final_state.get("after_screenshot"))
