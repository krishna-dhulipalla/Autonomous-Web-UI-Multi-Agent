import json
from pathlib import Path
from typing import List, Optional, Dict

from .scoring import persist_scored, select_top, score_element
from .types import AgentAState


def score_elements(state: AgentAState) -> AgentAState:
    """Score elements using the instruction and select top 10."""
    instruction = state.get("instruction") or ""
    elements = state.get("elements") or []
    tried_ids: List[str] = state.get("tried_ids") or []
    plan_steps: Optional[Dict] = state.get(
        "plan_steps")  # Get plan_steps from state

    if not instruction:
        raise RuntimeError("No instruction available for scoring.")

    # Inlined and modified select_top logic
    current_top_k = 10  # Default top_k
    
    # If form mode, increase top_k to capture more candidates
    is_form_mode = False
    if plan_steps and isinstance(plan_steps, dict) and plan_steps.get("type") == "form":
        is_form_mode = True
    elif any(kw in instruction.lower() for kw in ["fill", "form", "enter", "type", "select"]):
        is_form_mode = True
        
    if is_form_mode:
        current_top_k = 25
        
    print(f"[Ranker] Scoring elements. Instruction='{instruction[:50]}...' FormMode={is_form_mode} TopK={current_top_k}")

    scored = []
    for e in elements:
        s = score_element(e, instruction, tried_ids)

        # Boost elements that match form fields
        if plan_steps and isinstance(plan_steps, dict) and plan_steps.get("type") == "form":
            fields = plan_steps.get("fields", [])
            e_name = (e.get("name") or "").lower()
            for f in fields:
                f_label = (f.get("label") or "").lower()
                if f_label and f_label in e_name:
                    s += 3.0  # Strong boost for label match

        e_copy = {k: e.get(k) for k in ("id", "role", "name",
                                        "landmark", "playwright_snippet")}
        e_copy["score"] = s
        scored.append(e_copy)

    scored_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)
    top_k = scored_sorted[:current_top_k]

    # Persist scored results alongside the existing metadata
    run_dir = Path(state["run_dir"])
    meta_path = run_dir / "elements.json"
    base_meta = {}
    if meta_path.exists():
        try:
            base_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            base_meta = {}

    base_meta.setdefault("user_query", state.get("user_query"))
    base_meta.setdefault("screenshot", state.get("screenshot_path"))

    persist_scored(meta_path, base_meta, scored_sorted, top_k)

    # Debug: Save top candidates for this step
    step = state.get("step", 0)
    debug_path = run_dir / f"candidates_step_{step}.json"
    try:
        debug_path.write_text(json.dumps(top_k, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Ranker] Failed to write debug candidates: {e}")

    state["top_elements"] = top_k
    return state
