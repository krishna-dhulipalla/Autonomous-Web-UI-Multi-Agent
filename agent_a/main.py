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
    initial_state: AgentAState = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "user_query": query,
        "history": history or [],
        "screenshot_path": None,
        "elements": [],
        "instruction": None,
        "tried_ids": [],
        "top_elements": [],
        "action_plan": None,
        "after_screenshot": None,
        "playwright": None,
        "context": None,
        "page": None,
    }

    # Add a run label to make traces easier to read (let LangGraph manage run IDs)
    final_state = app.invoke(initial_state, config={"run_name": "agent_a_pipeline"})
    print("[AgentA] Run completed")
    return final_state


def print_summary(user_query: str, final_state: AgentAState) -> None:
    print("\n=== Agent A result ===")
    print("User query:", user_query)
    print("Run dir:", final_state.get("run_dir"))
    print("Instruction:", final_state.get("instruction"))
    print("Screenshot:", final_state.get("screenshot_path"))
    print("Elements JSON:", Path(final_state.get("run_dir", "")) / "elements.json")
    top = final_state.get("top_elements") or []
    if top:
        print("Top candidates (id, role, name, score):")
        for e in top:
            try:
                score_val = float(e.get("score", 0.0))
            except Exception:
                score_val = 0.0
            print(f"  - {e.get('id')} | {e.get('role')} | {e.get('name')} | score={score_val:.2f}")
    plan = final_state.get("action_plan")
    if plan:
        print("Action plan:", plan)
    if final_state.get("after_screenshot"):
        print("After-action screenshot:", final_state.get("after_screenshot"))
