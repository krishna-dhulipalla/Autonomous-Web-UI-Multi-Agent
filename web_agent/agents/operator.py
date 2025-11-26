import json
from pathlib import Path
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.types import AgentAState

DEBUG_ACTION_FILTERS = False


def _debug(msg: str) -> None:
    if DEBUG_ACTION_FILTERS:
        print(msg)


def format_candidates(candidates: List[dict]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- id={c.get('id')} | role={c.get('role')} | name={c.get('name')} | landmark={c.get('landmark')}"
        )
    return "\n".join(lines)


def _heuristic_match(value: str, name: str) -> str:
    """Return a semantic type for a value or element name.

    NOTE: Kept for future use, but no longer used in normalization.
    """
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
    step_num = state.get("step", 0)
    top = state.get("top_elements") or []
    if not top:
        raise RuntimeError("No top elements available for Agent B.")

    # Create role/name maps for validation
    role_by_id = {str(e.get("id")): (e.get("role") or "") for e in top}
    name_by_id = {str(e.get("id")): (e.get("name") or "") for e in top}

    instruction = state.get("instruction") or state.get("user_query") or ""
    plan_steps = state.get("plan_steps")
    field_hints = state.get("field_hints") or {}
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.1,
        timeout=30,
        max_retries=1,
    )

    system_msg = SystemMessage(
        content=(
            "You are **Agent B**, the low-level UI operator. You do NOT see screenshots.\n"
            "You receive:\n"
            "- A high-level `instruction` from Agent A (Navigator), which often includes a short description of the current UI context\n"
            "- An optional structured `plan_steps` (for forms)\n"
            "- A list of up to 10 DOM candidates with stable `target_id`, labels, roles, and hints\n"
            "- Optional `field_hints` containing ids that best match form fields (title, description, priority, assignee, labels, submit). Prefer these ids when mapping fields.\n"
            "\n"
            "Your job:\n"
            "- Interpret the instruction and UI context.\n"
            "- Produce a SMALL sequence of concrete UI actions that advances the instruction.\n"
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
            "  \"followup_hint\": \"Short note about what changed or what to expect next\",\n"
            "  \"maybe_done\": true | false\n"
            "}\n"
            "\n"
            "You must always set \"maybe_done\" explicitly to true or false.\n"
            "\n"
            "Set \"maybe_done\": true only when:\n"
            "1. The instruction or user goal clearly describes a finite task (change X to Y, apply filter Z, create issue, save changes), AND\n"
            "2. The actions you are returning include the final critical step for that task, such as:\n"
            "   - Filling the last required field to the requested value.\n"
            "   - Clicking a Save / Submit / Create / Apply / Done button.\n"
            "   - Applying the exact filter(s) mentioned in the instruction.\n"
            "\n"
            "In all other cases, set \"maybe_done\": false, for example:\n"
            "- Pure navigation (\"open Settings\", \"go to Profile\"), when more work is obviously needed afterwards.\n"
            "- Exploratory steps (\"open menu\", \"expand dropdown\") that just reveal more UI.\n"
            "- When you are unsure if this completes the goal.\n"
            "\n"
            "Example 1 – final field edit:\n"
            "{\n"
            "  \"actions\": [\n"
            "    {\"action\": \"fill\", \"target_id\": \"34\", \"params\": {\"text\": \"Krishna Vamsi\"}}\n"
            "  ],\n"
            "  \"followup_hint\": \"Updated the 'Full name' field.\",\n"
            "  \"maybe_done\": true\n"
            "}\n"
            "\n"
            "Example 2 – mid-navigation:\n"
            "{\n"
            "  \"actions\": [\n"
            "    {\"action\": \"click\", \"target_id\": \"4\", \"params\": {}}\n"
            "  ],\n"
            "  \"followup_hint\": \"Opened the Profile tab; you can now edit personal info.\",\n"
            "  \"maybe_done\": false\n"
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
            "- If `field_hints.<field>_ids` is provided, you must prefer those ids for the matching field label before considering other candidates.\n"
            "- For each field in `plan_steps.fields`, choose the most plausible candidate by label/role:\n"
            "  * text -> action: fill\n"
            "  * select/dropdown -> action: select (option = visible label)\n"
            "  * checkbox -> action: click (toggle) only if needed to match desired value\n"
            "  * date/date-relative -> prefer a date field if present; if only text is available, fill the provided value\n"
            "- If a combobox name clearly matches a form field label (e.g. 'Change assignee', 'Change labels'),\n"
            "  it is almost always WRONG to just click it with empty params.\n"
            "  * Prefer action: select with params.option taken from that field's value in `plan_steps`.\n"
            "  * If the control behaves like a typeahead, use action: fill with params.text.\n"
            "- Typical order: (1) open/focus form if needed (click), (2) fill/select all fields, (3) submit if `submit: true`.\n"
            "- If a required field has **no matching candidate in the top-10**, skip it and still return actions for the rest.\n"
            "\n"
            "====================\n"
            "WHEN `plan_steps` IS ABSENT (NON-FORM STEP)\n"
            "====================\n"
            "- Treat the instruction as a single next navigation/interaction step.\n"
            "- Use the context in the instruction (e.g. 'You are on the workspace menu…') to avoid re-opening menus\n"
            "  or clicking unrelated chrome.\n"
            "- For pure navigation or click steps (e.g. 'click the Settings option', 'open the issues tab'):\n"
            "  * Produce **exactly ONE** `click` action on the single best-matching candidate.\n"
            "  * Do NOT chain multiple preparatory clicks (e.g. 'click Workspace, then click Settings') in one response.\n"
            "    Agent A will issue follow-up instructions for additional steps.\n"
            "  * If the instruction describes only one control to interact with, return a single action.\n"
            "- Only include multiple actions in a non-form step when they are clearly part of one atomic interaction\n"
            "  (e.g. press a key immediately after a click to close a dialog), and keep this rare.\n"
            "\n"
            "====================\n"
            "SELECTION RULES\n"
            "====================\n"
            "- Match by label/accessibility name and role first. Prefer visible, enabled controls.\n"
            "- Use the context in the instruction to bias toward the right region: if it mentions a menu, dropdown,\n"
            "  or modal, prefer candidates that are likely inside that UI, instead of global navigation/toolbars.\n"
            "- When the instruction is to submit/create/update and you see multiple similar buttons\n"
            "  (e.g. 'Create new issue' in navigation vs 'Create issue' in the form),\n"
            "  prefer the button in the current form/modal instead of the global navigation control.\n"
            "- **CRITICAL**: For forms, map fields CAREFULLY. Do not put 'Due date' into 'Description'. Check labels closely.\n"
            "- Do NOT invent target_ids. Use only the provided candidates.\n"
            "- Keep the action list short and strictly necessary. No exploratory clicks.\n"
            "- Do not map two different form fields to the same target_id. Each field should use its own control.\n"
            "- If you cannot determine a concrete option or text from plan_steps or the goal, omit that action and\n"
            "  mention it in followup_hint instead of guessing or clicking blindly.\n"
            "- If ui_same is true in the history, do not choose the same target_id that was used last step. Pick a different\n"
            "  candidate that advances the goal.\n"
            "- For role=combobox, prefer select { option }. Do not use fill unless explicitly told it’s a typeahead and\n"
            "  no visible option appears.\n"
            "\n"
            "====================\n"
            "SAFETY & CONSISTENCY\n"
            "====================\n"
            "- Avoid destructive actions (delete/close/dismiss) unless clearly required by the instruction.\n"
            "- If a field value already appears correct in its label/hint, you may omit that action.\n"
            "- If nothing can be done with the provided candidates, return an empty actions list and a followup_hint\n"
            "  explaining what is missing.\n"
            "- **CRITICAL**: Do NOT output 'fill' action for elements with role 'button', 'link', 'tab', 'menuitem', or 'switch'.\n"
            "  Only 'textbox', 'combobox', 'searchbox', 'textarea', or similar input roles may be filled.\n"
            "\n"
            "====================\n"
            "RESPONSE REQUIREMENT\n"
            "====================\n"
            "- Return exactly one JSON object with keys `actions` and `followup_hint`.\n"
            "- Do not wrap the object in an array and do not include any extra text.\n"
            "- For simple navigation steps, the `actions` list MUST contain exactly one item.\n"
        )
    )

    history_tail = (state.get("history") or [])[-2:]
    ui_same = state.get("ui_same", False)
    plan_summary = "form" if plan_steps else "navigation"
    plan_flag = "present" if plan_steps is not None else "null"
    instr_preview = instruction if len(
        instruction) <= 200 else instruction[:197] + "..."
    print(
        f"[AgentB] Input step={step_num} mode={plan_summary} ui_same={ui_same} plan_steps={plan_flag} history_tail={history_tail}"
    )
    if plan_steps and isinstance(plan_steps, dict):
        print(
            f"[AgentB] Instruction='{instr_preview}' plan_fields={len(plan_steps.get('fields', []))} submit={bool(plan_steps.get('submit'))} candidates={len(top)} plan_steps={plan_flag}"
        )
    else:
        print(
            f"[AgentB] Instruction='{instr_preview}' candidates={len(top)} plan_steps={plan_flag}"
        )

    plan_json = json.dumps(
        plan_steps, indent=2) if plan_steps is not None else "null"
    field_hints_json = json.dumps(field_hints, indent=2)
    human_text = (
        f"User goal/instruction: {instruction}\n"
        f"Recent history (last {len(history_tail)}): {history_tail}\n"
        f"ui_same: {ui_same}\n"
        f"plan_steps (may be null):\n{plan_json}\n\n"
        f"field_hints (preferred ids per field):\n{field_hints_json}\n\n"
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
            [r.get("text", "") if isinstance(r, dict) else str(r) for r in raw]
        )
    else:
        raw_text = raw if isinstance(raw, str) else str(raw)

    raw_preview = raw_text if len(raw_text) <= 400 else raw_text[:397] + "..."
    print(f"[AgentB] Raw response (truncated): {raw_preview}")

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
            plan = {
                "actions": [plan],
                "followup_hint": plan.get("followup_hint", "")
                if isinstance(plan, dict)
                else "",
            }
    else:
        plan = {"actions": [], "followup_hint": ""}

    maybe_done = bool(plan.get("maybe_done", False)
                      ) if isinstance(plan, dict) else False
    actions = plan.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    elif not isinstance(actions, list):
        actions = []

    # --- Minimal normalization only: keep actions simple and safe ---
    normalized_actions: List[dict] = []
    seen_targets = set()

    for a in actions:
        if not isinstance(a, dict):
            continue
        if "params" not in a or not isinstance(a["params"], dict):
            a["params"] = {}

        action_type = a.get("action")
        tid_raw = a.get("target_id")
        if tid_raw is None:
            continue
        tid = str(tid_raw)

        # Enforce unique target_id (one field -> one control per step)
        if tid in seen_targets:
            _debug(f"[AgentB] Skipping duplicate action for target_id {tid}")
            continue
        seen_targets.add(tid)

        role = role_by_id.get(tid, "")

        # Minimal role-based guards
        if action_type == "fill":
            txt = a["params"].get("text") or a["params"].get("value")
            if not txt:
                print("[AgentB] Skipping fill without text")
                continue
            if role not in {"textbox", "textarea", "searchbox", "combobox", "contenteditable"}:
                print(
                    f"[AgentB] Skipping fill on non-input role {role} for {tid}")
                continue

        elif action_type == "select":
            opt = a["params"].get("option") or a["params"].get("value")
            if not opt:
                print("[AgentB] Skipping select without option")
                continue
            if role not in {"combobox", "menuitem"}:
                print(
                    f"[AgentB] Skipping select on non-select role {role} for {tid}")
                continue

        elif action_type == "press":
            key = a["params"].get("key")
            if not key:
                print("[AgentB] Skipping press without key")
                continue

        elif action_type == "click":
            # click is always allowed; executor will handle edge cases
            pass

        else:
            # Unknown or unsupported action type
            print(f"[AgentB] Skipping unsupported action type {action_type}")
            continue

        normalized_actions.append(a)

    followup_hint = plan.get("followup_hint", "")

    # No more ineffective_targets updates or suspect submit logic – keep it simple
    state["actions"] = normalized_actions
    state["followup_hint"] = followup_hint
    state["maybe_done"] = maybe_done

    # Persist actions for debugging
    run_dir = Path(state.get("run_dir", "."))
    step = state.get("step", 0)
    actions_path = run_dir / f"actions_step_{step}.json"
    try:
        actions_path.write_text(json.dumps(
            normalized_actions, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[AgentB] Failed to write actions.json: {e}")

    print(
        f"[AgentB] Output step={step_num} maybe_done={maybe_done} actions={normalized_actions} followup_hint='{followup_hint}'"
    )
    return state
