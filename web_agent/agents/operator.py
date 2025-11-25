import json
from pathlib import Path
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.types import AgentAState


def format_candidates(candidates: List[dict]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- id={c.get('id')} | role={c.get('role')} | name={c.get('name')} | landmark={c.get('landmark')}"
        )
    return "\n".join(lines)


def _heuristic_match(value: str, name: str) -> str:
    """Return a semantic type for a value or element name."""
    # Check both value and name for keywords
    text = (value + " " + name).lower()
    
    if "@" in text and "." in text:
        return "email"
    if any(x in text for x in ["high", "medium", "low", "urgent", "priority"]):
        return "priority"
    if any(x in text for x in ["bug", "feature", "improvement", "task", "label"]):
        return "label"
    return "other"


def agent_b(state: AgentAState) -> AgentAState:
    """Small LLM to choose one or more actions for the top-10 candidates."""
    top = state.get("top_elements") or []
    if not top:
        raise RuntimeError("No top elements available for Agent B.")

    # Create role map for validation
    role_by_id = {str(e.get("id")): (e.get("role") or "") for e in top}
    name_by_id = {str(e.get("id")): (e.get("name") or "") for e in top}

    instruction = state.get("instruction") or state.get("user_query") or ""
    plan_steps = state.get("plan_steps")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1,
                     timeout=30, max_retries=1)

    system_msg = SystemMessage(
        content=(
            "You are **Agent B**, the low-level UI operator. You do NOT see screenshots.\n"
            "You receive:\n"
            "- A high-level `instruction` from Agent A (Navigator)\n"
            "- An optional structured `plan_steps` (for forms)\n"
            "- A list of up to 10 DOM candidates with stable `target_id`, labels, roles, and hints\n"
            "\n"
            "Your job:\n"
            "- Produce a SMALL sequence of concrete UI actions that satisfies the instruction.\n"
            "- Use ONLY the provided candidates by their `target_id`.\n"
            "- Return JSON ONLY.\n"
            "\n"
            "====================\n"
            "OUTPUT FORMAT (JSON ONLY)\n"
            "====================\n"
            "{\n"
            "  \"actions\": [\n"
            "    {\"action\": \"click\" | \"fill\" | \"select\" | \"press\", \"target_id\": \"<id>\", \"params\": { ... }},\n"
            "    ...\n"
            "  ],\n"
            "  \"followup_hint\": \"Short note about what changed or what to expect next\"\n"
            "}\n"
            "\n"
            "Action params:\n"
            "- click:    { }\n"
            "- fill:     { \"text\": \"<string>\" }\n"
            "- select:   { \"option\": \"<visible label>\" }\n"
            "- press:    { \"key\": \"Enter|Tab|Escape|...\" }\n"
            "\n"
            "====================\n"
            "WHEN `plan_steps` (FORM) IS PROVIDED\n"
            "====================\n"
            "- Interpret `plan_steps` as a macro: fill ALL fields it lists, then submit if `submit` is true.\n"
            "- For each field in `plan_steps.fields`, choose the most plausible candidate by label/role:\n"
            "  * text -> action: fill\n"
            "  * select/dropdown -> action: select (option = visible label)\n"
            "  * checkbox -> action: click (toggle) only if needed to match desired value\n"
            "  * date/date-relative -> prefer a date field if present; if only text is available, fill the provided value\n"
            "- If a combobox name clearly matches a form field label (e.g. 'Change assignee', 'Change labels'),\n"
            "  it is almost always WRONG to just click it with empty params.\n"
            "  * Prefer action: select with params.option taken from that field's value in `plan_steps`.\n"
            "  * If the control behaves like a typeahead, use action: fill with params.text.\n"
            "- Order: (1) focus/open form if needed (click), (2) fill/select all fields, (3) submit if `submit: true`.\n"
            "- If a required field has **no matching candidate in the top-10**, skip it and still return actions for the rest.\n"
            "\n"
            "Example (FORM):\n"
            "{\n"
            "  \"actions\": [\n"
            "    {\"action\": \"fill\",   \"target_id\": \"13\", \"params\": {\"text\": \"testing\"}},\n"
            "    {\"action\": \"select\", \"target_id\": \"22\", \"params\": {\"option\": \"High\"}},\n"
            "    {\"action\": \"fill\",   \"target_id\": \"41\", \"params\": {\"text\": \"next week\"}},\n"
            "    {\"action\": \"click\",  \"target_id\": \"30\", \"params\": {}}\n"
            "  ],\n"
            "  \"followup_hint\": \"Form filled and submitted—expect navigation or a success toast.\"\n"
            "}\n"
            "\n"
            "====================\n"
            "WHEN `plan_steps` (NON-FORM STEP) IS ABSENT\n"
            "====================\n"
            "- Produce the minimal actions that advance the instruction (often 1–3 actions).\n"
            "- Examples: open a creation dialog, expand a menu, navigate a tab, confirm a blocking popup, etc.\n"
            "\n"
            "Example (NON-FORM):\n"
            "{\n"
            "  \"actions\": [\n"
            "    {\"action\": \"click\", \"target_id\": \"25\", \"params\": {}}\n"
            "  ],\n"
            "  \"followup_hint\": \"Opens the issue creation form modal.\"\n"
            "}\n"
            "\n"
            "====================\n"
            "SELECTION RULES\n"
            "====================\n"
            "- Match by label/accessibility name and role first. Prefer visible, enabled controls.\n"
            "- Prefer controls that are likely inside the active form/modal (same region as other fields),\n"
            "  over navigation/toolbar items that live far away from the form.\n"
            "- If multiple candidates look valid, choose the one that best fits context (e.g., in a form region or modal).\n"
            "- When the instruction is to submit/create/update and you see multiple similar buttons\n"
            "  (e.g. 'Create new issue' in navigation vs 'Create issue' in the form),\n"
            "  prefer the button in the current form/modal instead of the global navigation control.\n"
            "- **CRITICAL**: For forms, map fields CAREFULLY. Do not put 'Due date' into 'Description'. Check labels closely.\n"
            "- Do NOT invent target_ids. Use only the provided candidates.\n"
            "- Keep the action list short and strictly necessary. No exploratory clicks.\n"
            "- Do not map two different form fields to the same target_id. Each field should use its own control.\n"
            "- If you cannot determine a concrete option or text from plan_steps or the goal, omit that action and mention it in followup_hint instead of guessing or clicking blindly.\n"
            "- If ui_same is true in the history, do not choose the same target_id that was used last step. Pick a different candidate that advances the goal.\n"
            "- For role combobox, prefer select { option }. Do not use fill unless explicitly told it’s a typeahead and no visible option appears.\n"
            "\n"
            "====================\n"
            "SAFETY & CONSISTENCY\n"
            "====================\n"
            "- Avoid destructive actions (delete/close/dismiss) unless clearly required by the instruction.\n"
            "- If a field value already appears correct in its label/hint, you may omit that action.\n"
            "- If nothing can be done with the provided candidates, return an empty actions list and a followup_hint explaining what is missing.\n"
            "- **CRITICAL**: Do NOT output 'fill' action for elements with role 'button', 'link', 'tab', 'menuitem', or 'switch'.\n"
            "  Only 'textbox', 'combobox', 'searchbox', or 'textarea' can be filled.\n"
            "- If the instruction is to finish or submit an operation (e.g. 'create issue', 'save changes') and there is both\n"
            "  a navigation-level button and an in-form button with similar text, treat the in-form button as the correct target.\n"
            "\n"
            "====================\n"
            "RESPONSE REQUIREMENT\n"
            "====================\n"
            "- Return exactly one JSON object with keys actions and followup_hint. Do not wrap the object in an array and do not include any extra text.\n"
        )
    )
    plan_json = json.dumps(
        plan_steps, indent=2) if plan_steps is not None else "null"
    human_text = (
        f"User goal/instruction: {instruction}\n\n"
        f"plan_steps (may be null):\n{plan_json}\n\n"
        "Candidates (id, role, name, landmark):\n"
        f"{format_candidates(top)}\n\n"
        "Return JSON as specified in the system message."
    )
    human_msg = HumanMessage(content=human_text)

    try:
        raw = llm.invoke([system_msg, human_msg]).content
    except Exception as e:
        print(f"[AgentB] Model call failed: {e}")
        raise

    if isinstance(raw, list):
        raw_text = "".join(
            [r.get("text", "") if isinstance(r, dict) else str(r) for r in raw])
    else:
        raw_text = raw if isinstance(raw, str) else str(raw)

    plan = None
    try:
        plan = json.loads(raw_text)
    except Exception:
        # try to extract JSON snippet
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                plan = json.loads(raw_text[start: end + 1])
            except Exception:
                raise RuntimeError(f"Agent B returned non-JSON: {raw_text}")
        else:
            raise RuntimeError(f"Agent B returned non-JSON: {raw_text}")

    # Normalize to a dict with top-level "actions" list
    if isinstance(plan, list):
        if len(plan) == 1 and isinstance(plan[0], dict) and "actions" in plan[0]:
            plan = plan[0]
        else:
            plan = {"actions": plan}

    if isinstance(plan, dict):
        if "actions" not in plan:
            # single action object
            plan = {"actions": [plan], "followup_hint": plan.get(
                "followup_hint", "") if isinstance(plan, dict) else ""}
    else:
        plan = {"actions": [], "followup_hint": ""}

    actions = plan.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    elif not isinstance(actions, list):
        actions = []

    # ensure params present and unique targets; enforce select/fill safety
    normalized_actions = []
    seen_targets = set()
    for a in actions:
        if not isinstance(a, dict):
            continue
        if "params" not in a or not isinstance(a["params"], dict):
            a["params"] = {}

        action_type = a.get("action")
        tid = a.get("target_id")
        
        # --- Normalization & Correction ---
        
        # 1. Auto-convert fill -> select for combobox
        role = role_by_id.get(str(tid), "")
        if action_type == "fill" and role == "combobox":
            text_val = a["params"].get("text") or a["params"].get("value")
            if text_val:
                print(f"[AgentB] Converting fill('{text_val}') -> select('{text_val}') for combobox {tid}")
                a["action"] = "select"
                a["params"] = {"option": text_val}
                action_type = "select"

        # 2. Semantic Remapping (Swap target if value type mismatches target name)
        # Only applies to select/fill where we have a value
        val_to_check = None
        if action_type == "select":
            val_to_check = a["params"].get("option")
        elif action_type == "fill":
            val_to_check = a["params"].get("text")
            
        if val_to_check and tid:
            current_name = name_by_id.get(str(tid), "")
            val_type = _heuristic_match(val_to_check, "")
            name_type = _heuristic_match("", current_name)
            
            # If types differ and are specific (not 'other'), try to find a better target
            # We allow swapping if val_type is known (e.g. priority) and target is either unknown or different
            if val_type != "other" and val_type != name_type:
                print(f"[AgentB] Semantic mismatch: value='{val_to_check}' ({val_type}) vs target='{current_name}' ({name_type})")
                # Look for a better candidate in top elements
                best_swap = None
                for cand in top:
                    c_id = str(cand.get("id"))
                    c_name = cand.get("name") or ""
                    c_type = _heuristic_match("", c_name)
                    if c_type == val_type and c_id not in seen_targets:
                        best_swap = c_id
                        print(f"[AgentB] Found better swap candidate: {c_id} ('{c_name}')")
                        break
                
                if best_swap:
                    print(f"[AgentB] Swapping target {tid} -> {best_swap}")
                    tid = best_swap
                    a["target_id"] = best_swap
                    # Update role for the new target to ensure subsequent checks pass
                    role = role_by_id.get(str(tid), "")

        # Enforce unique target_id (one field -> one control)
        if tid:
            if tid in seen_targets:
                print(f"[AgentB] Skipping duplicate action for target_id {tid}")
                continue
            seen_targets.add(tid)

        # Role-based guards
        if action_type == "fill" and role not in {"textbox", "textarea", "searchbox", "combobox", "contenteditable"}:
            print(f"[AgentB] Skipping fill on non-input role {role} for {tid}")
            continue
        if action_type == "select" and role not in {"combobox", "menuitem"}:
            print(f"[AgentB] Skipping select on non-select role {role} for {tid}")
            continue

        # Require params for select/fill
        if action_type == "select":
            opt = a["params"].get("option") or a["params"].get("value")
            if not opt:
                print("[AgentB] Skipping select without option")
                continue
        if action_type == "fill":
            txt = a["params"].get("text") or a["params"].get("value")
            if not txt:
                print("[AgentB] Skipping fill without text")
                continue

        normalized_actions.append(a)

    followup_hint = plan.get("followup_hint", "")

    state["actions"] = normalized_actions
    state["followup_hint"] = followup_hint

    # Persist actions for debugging
    run_dir = Path(state.get("run_dir", "."))
    step = state.get("step", 0)
    actions_path = run_dir / f"actions_step_{step}.json"
    try:
        actions_path.write_text(json.dumps(
            normalized_actions, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[AgentB] Failed to write actions.json: {e}")

    print(f"[AgentB] Actions: {actions}")
    return state
