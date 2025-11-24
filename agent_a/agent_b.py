import json
from pathlib import Path
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .types import AgentAState


def format_candidates(candidates: List[dict]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- id={c.get('id')} | role={c.get('role')} | name={c.get('name')} | landmark={c.get('landmark')}"
        )
    return "\n".join(lines)


def agent_b(state: AgentAState) -> AgentAState:
    """Small LLM to choose one or more actions for the top-10 candidates."""
    top = state.get("top_elements") or []
    if not top:
        raise RuntimeError("No top elements available for Agent B.")

    instruction = state.get("instruction") or state.get("user_query") or ""
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
            "WHEN `plan_steps` IS ABSENT (NON-FORM STEP)\n"
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
            "- If multiple candidates look valid, choose the one that best fits context (e.g., in a form region or modal).\n"
            "- **CRITICAL**: For forms, map fields CAREFULLY. Do not put 'Due date' into 'Description'. Check labels closely.\n"
            "- Do NOT invent target_ids. Use only the provided candidates.\n"
            "- Keep the action list short and strictly necessary. No exploratory clicks.\n"
            "\n"
            "====================\n"
            "SAFETY & CONSISTENCY\n"
            "====================\n"
            "- Avoid destructive actions (delete/close/dismiss) unless clearly required by the instruction.\n"
            "- If a field value already appears correct in its label/hint, you may omit that action.\n"
            "- If nothing can be done with the provided candidates, return an empty actions list and a followup_hint explaining what is missing.\n"
            "- **CRITICAL**: Do NOT output 'fill' action for elements with role 'button', 'link', 'tab', 'menuitem', or 'switch'. Only 'textbox', 'combobox', 'searchbox', or 'textarea' can be filled.\n"
            "\n"
            "====================\n"
            "RESPONSE REQUIREMENT\n"
            "====================\n"
            "- Return exactly one JSON object with keys actions and followup_hint. Do not wrap the object in an array and do not include any extra text.\n"
        )
    )

    human_text = (
        f"User goal/instruction: {instruction}\n\n"
        "Candidates (id, role, name, landmark):\n"
        f"{format_candidates(top)}\n\n"
        "Choose one id from the list above and output JSON as specified."
    )
    human_msg = HumanMessage(content=human_text)

    try:
        raw = llm.invoke([system_msg, human_msg]).content
    except Exception as e:
        print(f"[AgentB] Model call failed: {e}")
        raise

    if isinstance(raw, list):
        raw_text = "".join([r.get("text", "") if isinstance(r, dict) else str(r) for r in raw])
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
            plan = {"actions": [plan], "followup_hint": plan.get("followup_hint", "") if isinstance(plan, dict) else ""}
    else:
        plan = {"actions": [], "followup_hint": ""}

    actions = plan.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    elif not isinstance(actions, list):
        actions = []

    # ensure params present
    normalized_actions = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        if "params" not in a or not isinstance(a["params"], dict):
            a["params"] = {}
        normalized_actions.append(a)

    followup_hint = plan.get("followup_hint", "")

    state["actions"] = normalized_actions
    state["followup_hint"] = followup_hint

    # Persist actions for debugging
    run_dir = Path(state.get("run_dir", "."))
    step = state.get("step", 0)
    actions_path = run_dir / f"actions_step_{step}.json"
    try:
        actions_path.write_text(json.dumps(normalized_actions, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[AgentB] Failed to write actions.json: {e}")

    print(f"[AgentB] Actions: {actions}")
    return state
