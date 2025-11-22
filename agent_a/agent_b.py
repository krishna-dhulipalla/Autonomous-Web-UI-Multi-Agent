import json
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
    """Small LLM to choose an action for one of the top-10 candidates."""
    top = state.get("top_elements") or []
    if not top:
        raise RuntimeError("No top elements available for Agent B.")

    instruction = state.get("instruction") or state.get("user_query") or ""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1, timeout=30, max_retries=1)

    system_msg = SystemMessage(
        content=(
    "You are **Operator**, also known as Agent B.\n"
    "Your job is to take the planner's instruction (from Agent A) and choose exactly ONE UI element "
    "from the provided candidate list. Each element has: id, name, role, and sometimes landmark.\n\n"

    "====================\n"
    "WHAT YOU CAN DO\n"
    "====================\n"
    "You choose ONE action from this list:\n"
    "- click\n"
    "- fill\n"
    "- select\n"
    "- press\n\n"

    "Rules:\n"
    "- The chosen target_id MUST be one of the provided candidates.\n"
    "- If the action is 'fill', include params.text with the value to type.\n"
    "- If the action is 'select', include params.option with the value to pick.\n"
    "- For 'click' or 'press', params can be {}.\n"
    "- Prefer the simplest action that advances the planner's instruction.\n"
    "- You do NOT see the screenshot—only names, roles, and the planner instruction.\n"
    "- Avoid guessing: pick the candidate whose name and role best match the instruction.\n\n"

    "====================\n"
    "OUTPUT FORMAT\n"
    "====================\n"
    "Respond with a JSON object. Do NOT wrap it in backticks or explanations.\n"
    "Example:\n"
    "{\n"
    "  \"action\": \"click\",\n"
    "  \"target_id\": \"28\",\n"
    "  \"params\": {},\n"
    "  \"followup_hint\": \"opens a creation form\"\n"
    "}\n\n"

    "If the instruction clearly requires filling multiple fields, "
    "you may choose one field at a time (MVP design), unless the planner explicitly tells you "
    "to fill the whole form.\n\n"

    "Keep responses short, direct, and JSON-only."
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

    try:
        plan = json.loads(raw_text)
    except Exception:
        # try to extract JSON snippet
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                plan = json.loads(raw_text[start : end + 1])
            except Exception:
                raise RuntimeError(f"Agent B returned non-JSON: {raw_text}")
        else:
            raise RuntimeError(f"Agent B returned non-JSON: {raw_text}")

    state["action_plan"] = plan
    print(f"[AgentB] Plan: {plan}")
    return state

