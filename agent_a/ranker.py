import json
from pathlib import Path
from typing import List, Optional, Dict

from .scoring import persist_scored, score_element
from .types import AgentAState


def score_elements(state: AgentAState) -> AgentAState:
    """Score elements using the instruction and select top 10."""
    instruction = state.get("instruction") or ""
    elements = state.get("elements") or []
    tried_ids = state.get("tried_ids") or []
    ui_same = state.get("ui_same", False)
    plan_steps: Optional[Dict] = state.get(
        "plan_steps")  # Get plan_steps from state

    if not instruction:
        raise RuntimeError("No instruction available for scoring.")

    # Inlined and modified select_top logic
    current_top_k = 15  # Default top_k
    
    # If form mode, increase top_k to capture more candidates
    is_form_mode = False
    if plan_steps and isinstance(plan_steps, dict) and plan_steps.get("type") == "form":
        is_form_mode = True
    else:
        # Stricter check: must look like a form-filling instruction
        instr_lc = instruction.lower()
        if "fill" in instr_lc and ("form" in instr_lc or "details" in instr_lc):
            is_form_mode = True
        
    if is_form_mode:
        current_top_k = 25
        
    print(f"[Ranker] Scoring elements. Instruction='{instruction[:50]}...' FormMode={is_form_mode} TopK={current_top_k} UI_Same={ui_same}")

    scored = []
    for e in elements:
        s = score_element(e, instruction, tried_ids, ui_same)

        # Boost elements that match form fields
        if plan_steps and isinstance(plan_steps, dict) and plan_steps.get("type") == "form":
            fields = plan_steps.get("fields", [])
            e_name = (e.get("name") or "").lower()
            e_placeholder = (e.get("placeholder") or "").lower()
            for f in fields:
                f_label = (f.get("label") or "").lower()
                if f_label and (f_label in e_name or f_label in e_placeholder):
                    s += 3.0  # Strong boost for label match

        e_copy = {k: e.get(k) for k in ("id", "role", "name",
                                        "landmark", "playwright_snippet", "placeholder")}
        e_copy["score"] = s
        scored.append(e_copy)

    scored_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)

    selected = []
    used_ids = set()

    # baseline top_k
    for e in scored_sorted:
        if len(selected) >= current_top_k:
            break
        selected.append(e)
        used_ids.add(e["id"])

    instr_lc = instruction.lower()
    # ensure some inputs for fill instructions
    if any(tok in instr_lc for tok in ["fill", "title", "description", "field"]):
        # Include textbox, textarea, searchbox, contenteditable
        inputs = [
            e
            for e in scored_sorted
            if e.get("role") in ("textbox", "textarea", "searchbox", "contenteditable")
            and e["id"] not in used_ids
        ]
        for e in inputs[:5]:
            selected.append(e)
            used_ids.add(e["id"])

    # ensure some comboboxes for select instructions
    if any(tok in instr_lc for tok in ["select", "dropdown", "choose", "option"]):
        combos = [
            e for e in scored_sorted if e.get("role") == "combobox" and e["id"] not in used_ids
        ]
        for e in combos[:5]:
            selected.append(e)
            used_ids.add(e["id"])

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

    persist_scored(meta_path, base_meta, scored_sorted, selected)

    # Debug: Save top candidates for this step
    step = state.get("step", 0)
    debug_path = run_dir / f"candidates_step_{step}.json"
    try:
        debug_path.write_text(json.dumps(selected, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Ranker] Failed to write debug candidates: {e}")

    state["top_elements"] = selected
    return state
