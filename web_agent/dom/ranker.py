import json
from pathlib import Path
from typing import List, Optional, Dict

from .scoring import persist_scored, score_element
from ..core.types import AgentAState


def score_elements(state: AgentAState) -> AgentAState:
    """Score elements using the instruction and select top 10."""
    instruction = state.get("instruction") or ""
    elements = state.get("elements") or []
    tried_ids = state.get("tried_ids") or []
    ineffective_targets = state.get("ineffective_targets") or []
    ui_same = state.get("ui_same", False)
    plan_steps: Optional[Dict] = state.get(
        "plan_steps")  # Get plan_steps from state

    if not instruction:
        raise RuntimeError("No instruction available for scoring.")

    # Inlined and modified select_top logic
    current_top_k = 10  # Default top_k (non-form)

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

    print(
        f"[Ranker] Scoring elements. Instruction='{instruction[:50]}...' FormMode={is_form_mode} TopK={current_top_k} UI_Same={ui_same}")

    scored = []
    for e in elements:
        s = score_element(e, instruction, tried_ids, ui_same)

        # Penalize ineffective targets
        if e["id"] in ineffective_targets:
            s -= 10.0

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
                                        "landmark", "playwright_snippet", "placeholder", "value")}
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

    # Persist scored results per step (no global elements.json)
    run_dir = Path(state["run_dir"])
    step = state.get("step", 0)
    meta_path = run_dir / f"elements_scored_step_{step}.json"
    base_meta = {
        "user_query": state.get("user_query"),
        "screenshot": state.get("screenshot_path"),
    }
    persist_scored(meta_path, base_meta, scored_sorted, selected)

    # Debug: Save top candidates for this step
    debug_path = run_dir / f"candidates_step_{step}.json"
    try:
        debug_path.write_text(json.dumps(selected, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Ranker] Failed to write debug candidates: {e}")

    # Debug: Save full elements with instruction for this step
    elements_debug_path = run_dir / f"elements_step_{step}.json"
    try:
        elements_payload = {
            "instruction": instruction,
            "elements": elements,
        }
        elements_debug_path.write_text(json.dumps(elements_payload, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[Ranker] Failed to write elements debug file: {e}")

    state["top_elements"] = selected
    return state
