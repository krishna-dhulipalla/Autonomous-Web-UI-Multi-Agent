import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.types import AgentAState
from ..utils.imaging import image_to_data_url


def is_dom_tractable(user_query: str, elements: List[Dict[str, Any]]) -> bool:
    """
    Check if the user query can likely be solved by DOM labels alone.
    Returns True if we find a strong lexical match between the query and an actionable element.
    """
    # 1. Extract meaningful tokens from query (simple stopword removal)
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "for",
                 "of", "with", "by", "click", "go", "open", "select"}
    query_tokens = [t.lower() for t in re.split(r"\W+", user_query)
                    if t.lower() and t.lower() not in stopwords]

    if not query_tokens:
        return False

    # 2. Check against elements
    for elem in elements:
        name = (elem.get("name") or "").lower()
        if not name:
            continue

        # Exact phrase match (e.g. "my issues" in "go to my issues")
        if name in user_query.lower():
            return True

        # Token overlap
        name_tokens = set(re.split(r"\W+", name))
        # If all significant query tokens are present in the name (e.g. "profile settings" -> "settings")
        # Or if the name is fully contained in the query tokens
        common = name_tokens.intersection(query_tokens)
        if len(common) >= 1 and len(name_tokens) <= 3:
            # Strong signal: short element name matches a query token
            return True

    return False


def is_form_like(elements: List[Dict[str, Any]], user_query: str) -> bool:
    input_roles = {
        "textbox",
        "textarea",
        "searchbox",
        "combobox",
        "checkbox",
        "radio",
        "contenteditable",
    }
    submit_keywords = {"save", "create", "update", "submit", "apply", "done"}

    inputs = [e for e in elements if (e.get("role") or "") in input_roles]
    submit_buttons = [
        e
        for e in elements
        if (e.get("role") or "") == "button"
        and any(kw in (e.get("name") or "").lower() for kw in submit_keywords)
    ]

    if len(inputs) >= 3 and submit_buttons:
        # Check goal hints for multi-field intent
        goal_lc = user_query.lower()
        if any(tok in goal_lc for tok in ["fill", "enter", "update", "set", ","]):
            return True
    return False


def check_goal_satisfied(user_query: str, elements: List[Dict[str, Any]]) -> bool:
    """
    Fast DOM-based check: does the UI state clearly satisfy the goal?
    """
    # Heuristic 1: Value match in inputs
    # Extract potential target values from quotes or simple heuristics
    target_values = re.findall(r"['\"](.*?)['\"]", user_query)

    if not target_values:
        # Fallback: try to extract "to X" stopping at common prepositions
        # Matches "to X" where X ends at " in ", " on ", " at ", or end of string
        match = re.search(
            r"to\s+(.+?)(?:\s+(?:in|on|at|from|with)\s+|$)", user_query, re.IGNORECASE)
        if match:
            target_values.append(match.group(1).strip())

    print(
        f"[Planner] check_goal_satisfied: Checking for values {target_values}")

    for val in target_values:
        if not val:
            continue
        val_lower = val.lower()
        # Check if any input element has this value
        for elem in elements:
            role = elem.get("role", "")
            if role in {"textbox", "textarea", "combobox", "searchbox"}:
                curr_val = str(elem.get("value") or "").lower()
                if val_lower in curr_val:
                    print(f"[Planner] Goal satisfied: Found '{val}' in input.")
                    return True

    return False


def verify_completion(state: AgentAState, prefer_after: bool = False) -> bool:
    """
    Slow Vision-based check: ask LLM if the screenshot satisfies the goal.
    """
    snapshot = None
    if prefer_after and state.get("after_screenshot"):
        snapshot = state.get("after_screenshot")
        print(f"[Planner] Using after-action screenshot for verification: {snapshot}")
    elif state.get("screenshot_path"):
        snapshot = state.get("screenshot_path")
    else:
        return False

    if not snapshot:
        return False

    print("[Planner] Verifying completion with Vision LLM...")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, timeout=30)

    screenshot_path = Path(snapshot)
    data_url = image_to_data_url(screenshot_path, max_size=720)

    system_msg = SystemMessage(
        content="You are a verification agent. Compare the user's goal with the screenshot. Respond with JSON: {\"satisfied\": true/false, \"reason\": \"...\"}"
    )
    human_msg = HumanMessage(
        content=[
            {"type": "text", "text": f"User Goal: {state['user_query']}"},
            {"type": "image_url", "image_url": {"url": data_url}}
        ]
    )

    try:
        result = llm.invoke([system_msg, human_msg])
        content = result.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        parsed = json.loads(content)
        satisfied = parsed.get("satisfied", False)
        print(
            f"[Planner] Verification result: {satisfied} ({parsed.get('reason')})")
        return satisfied
    except Exception as e:
        print(f"[Planner] Verification failed: {e}")
        return False


def decide_planning_mode(state: AgentAState, elements: List[Dict[str, Any]], user_query: str) -> str:
    """
    Decide planning mode per step:
    - vision: full vision+LLM (Navigator)
    - dom_form: DOM + LLM (no image) for forms
    - dom: DOM-only (no LLM)
    """
    step_index = state.get("step", 0)
    last_mode = state.get("planning_mode")
    ui_same = state.get("ui_same", False)
    last_actions = state.get("last_actions") or []
    plan_steps = state.get("plan_steps")

    # Force vision if first step or DOM attempts didn't change UI
    if step_index == 0 or (ui_same and last_mode == "dom") or (last_mode == "dom" and not last_actions):
        print("[Planner] Force Vision (first step or DOM no-change)")
        return "vision"

    # Form detection
    if is_form_like(elements, user_query):
        print("[Planner] Form-like screen -> DOM+LLM form mode")
        return "dom_form"

    # Strong single-label match
    if is_dom_tractable(user_query, elements):
        print("[Planner] DOM tractable -> DOM-only")
        return "dom"

    print("[Planner] Default -> Vision")
    return "vision"


def agent_a(state: AgentAState) -> AgentAState:
    """Planner: Routes between Vision LLM and DOM-only path."""

    user_query = state["user_query"]
    elements = state.get("elements", [])
    maybe_done_signal = bool(state.get("maybe_done"))
    # Clear the flag so we don't loop on it across steps; we keep the signal locally.
    state["maybe_done"] = False

    # --- Goal Verification ---

    # 1. Fast DOM Check (Always run)
    if check_goal_satisfied(user_query, elements):
        print("[Planner] DOM check passed. Goal completed.")
        state["done"] = True
        state["completion_via"] = "dom_check"
        return state

    # 2. Slow Vision Check (Only if signal received)
    if maybe_done_signal:
        print(
            "[Planner] maybe_done from Agent B -> DOM not confirmed, running vision verification.")
        if verify_completion(state, prefer_after=True):
            print("[Planner] Vision check passed. Goal completed.")
            state["done"] = True
            state["completion_via"] = "vision_verification"
            return state
        print(
            "[Planner] Vision verification did not confirm completion. Continuing planning.")

    # Decide mode
    mode = decide_planning_mode(state, elements, user_query)
    state["planning_mode"] = mode

    step = state.get("step", 0)
    mode_readable = {
        "dom": "DOM-only",
        "dom_form": "DOM+LLM (form)",
        "vision": "Vision+LLM",
    }.get(mode, mode)
    print(f"[Planner] Step={step} planning via {mode_readable}")

    # --- DOM-Only Path ---
    if mode == "dom":
        instr = user_query
        if state.get("ineffective_targets"):
            instr += " (Note: Previous attempts on some elements failed. Try a different target.)"
        state["instruction"] = instr
        state["plan_steps"] = None
        state["done"] = False
        return state

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1,
                     timeout=45, max_retries=1)

    system_msg = SystemMessage(
        content=(
            "You are **Navigator**, a high-level planning agent that guides another agent (Agent B) to operate arbitrary web applications.\n"
            "\n"
            "You may be invoked in two modes:\n"
            "- Vision navigation mode: you see the screenshot plus the user goal and short history.\n"
            "- DOM/form mode: you see the user goal, history, and a DOM/field list (text-only). Use that DOM list to reason about forms and fields.\n"
            "\n"
            "Common inputs you always see:\n"
            "- The user's overall goal\n"
            "- A short history of previous steps and their outcomes\n"
            "\n"
            "You CANNOT click or type. You only decide the NEXT logical step and describe it as an instruction for Agent B.\n"
            "Agent B does not see the screenshot. Agent B only sees DOM elements and their labels/accessible names, and can perform actions like clicking, filling fields, and selecting options.\n"
            "\n"
            "Your job is to help Agent B reach the user's final goal safely and efficiently.\n"
            "\n"
            "====================\n"
            "HOW YOU REASON\n"
            "====================\n"
            "1. Understand the user's goal.\n"
            "   - Infer what final state the user wants (e.g., create a new record/item/document, filter a list, open a detail page, update fields, complete a form, etc.).\n"
            "\n"
            "2. Understand the current UI from the screenshot.\n"
            "   - Identify what kind of page or screen this is (dashboard, list view, detail view, settings, modal dialog, form, etc.).\n"
            "   - Notice whether the user is at the beginning of the flow, in the middle, or near completion.\n"
            "   - Detect if a modal or dialog is open and what it seems to be for.\n"
            "   - Detect blocking states: login screens, popups, error banners, or dialogs that prevent interaction with the main content.\n"
            "\n"
            "3. Use history to understand progress.\n"
            "   - If a previous instruction was followed and the UI changed appropriately, continue the workflow.\n"
            "   - If the UI did not change or looks inconsistent with the previous instruction, adjust your plan instead of repeating the same step blindly.\n"
            "   - If the previous step executed but the UI is unchanged (ui_same: true), assume the last approach failed. Do not repeat the same instruction. Propose an alternative path (e.g., pick a different control, navigate to the right section, open the correct modal).\n"
            "   - Avoid loops.\n"
            "\n"
            "4. Plan ONE next conceptual step.\n"
            "   - The step must be something Agent B can execute using DOM labels and structure.\n"
            "   - At the START of the `instruction` string, briefly describe the current UI context for Agent B\n"
            "     (e.g., 'You are currently on the workspace dropdown menu; now click the Settings option.').\n"
            "   - Then state the concrete next step that Agent B should try.\n"
            "   - If the current screen is a relevant form and the goal requires submitting it, then propose a single macro step to fill the entire form.\n"
            "     Provide a high-level field plan using `plan_steps` (see format below). Do NOT emit micro actions here.\n"
            "   - Otherwise, propose a non-form step (e.g., open a menu, navigate, open a creation form, resolve a blocking popup, etc.).\n"
            "\n"
            "5. Detect when the goal is completed."
            "   - Before proposing any action, carefully compare the user’s goal with the current UI state."
            "   - If the UI already satisfies the goal, mark the goal as complete and do NOT ask Agent B to perform anything."
            "   - Do NOT propose clicks, fills, or navigation when the requested change is already present."
            "   - When unsure, prefer waiting or re-checking instead of performing actions that could undo a correct state."
            "====================\n"
            "HOW TO REFER TO UI ELEMENTS\n"
            "====================\n"
            "- DO NOT use coordinates, pixel positions, or vague directions like 'top left', 'near the middle', or 'button on the right'.\n"
            "- DO NOT instruct based on raw symbols like '+' alone.\n"
            "- INSTEAD, describe the semantic purpose of the control so Agent B can match it to a DOM label or accessible name.\n"
            "\n"
            "Examples of good references:\n"
            "- \"Click the button labeled 'Create new item' if such a label exists.\"\n"
            "- \"Open the creation form using the main 'New' or 'Create' control on the page.\"\n"
            "- \"Fill the field labeled 'Title' with the user's title.\" \n"
            "- \"Select the option 'High' from the priority dropdown.\" \n"
            "\n"
            "====================\n"
            "RESPONSE SCHEMA (JSON ONLY)\n"
            "====================\n"
            "Always respond with a single JSON object with keys:\n"
            "- instruction: string – the next step description for Agent B, starting with a short UI context\n"
            "- reason: string – your brief reasoning\n"
            "- done: boolean – whether the goal is fully completed\n"
            "- plan_steps: object | null – present ONLY when the step is a form macro\n"
            "\n"
            "Non-form step example:\n"
            "{\n"
            "  \"instruction\": \"You are on the issues list with the workspace menu closed; click the workspace menu button to open it.\",\n"
            "  \"reason\": \"We must open the workspace menu to reach profile settings.\",\n"
            "  \"done\": false,\n"
            "  \"plan_steps\": null\n"
            "}\n"
            "\n"
            "Form step example (provide ALL fields in plan_steps):\n"
            "{\n"
            "  \"instruction\": \"You are on the creation form; fill it with the provided details and then submit.\",\n"
            "  \"reason\": \"The form is visible; completing it progresses directly to the goal.\",\n"
            "  \"done\": false,\n"
            "  \"plan_steps\": {\n"
            "    \"type\": \"form\",\n"
            "    \"form_name\": \"Generic creation form\",\n"
            "    \"fields\": [\n"
            "      {\"label\": \"Title\", \"value\": \"Example title\", \"kind\": \"text\"},\n"
            "      {\"label\": \"Priority\", \"value\": \"High\", \"kind\": \"select\"},\n"
            "      {\"label\": \"Due date\", \"value\": \"next week\", \"kind\": \"date-relative\"}\n"
            "    ],\n"
            "    \"submit\": true\n"
            "  }\n"
            "}\n"
            "\n"
            "Goal already completed example:\n"
            "{\n"
            "  \"instruction\": \"Goal completed.\",\n"
            "  \"reason\": \"The UI shows the final expected state.\",\n"
            "  \"done\": true,\n"
            "  \"plan_steps\": null\n"
            "}\n"
            "\n"
            "Blocked state example:\n"
            "{\n"
            "  \"instruction\": \"You are blocked by a dialog; click its primary confirmation button, then reopen the creation form.\",\n"
            "  \"reason\": \"A blocking dialog prevents interaction with the main content.\",\n"
            "  \"done\": false,\n"
            "  \"plan_steps\": null\n"
            "}\n"
        )
    )

    history_list = state.get("history") or []
    history_tail = history_list[-2:] if len(history_list) > 2 else history_list
    history_text = f"History (last {len(history_tail)}): {history_tail}"
    if state.get("ui_same"):
        history_text += f"; ui_same: true; last_tried_ids: {state.get('tried_ids', [])[-5:]}"

    human_content: List[Dict[str, Any]] = []
    if mode == "dom_form":
        top_snippets = []
        for e in elements[:36]:
            top_snippets.append(
                f"id={e.get('id')} role={e.get('role')} name={e.get('name')} landmark={e.get('landmark')}")
        human_content = [
            {"type": "text", "text": "Mode: DOM/form (no screenshot). Use the DOM list to build plan_steps and reason about fields.\n"
                                     f"User goal: {state['user_query']}\n"
                                     f"{history_text}\n"
                                     f"DOM snapshot (top {len(top_snippets)}):\n" + "\n".join(top_snippets)}
        ]
    else:
        if not state.get("screenshot_path"):
            raise RuntimeError("No screenshot available for Agent A.")
        screenshot_path = Path(state["screenshot_path"])
        data_url = image_to_data_url(screenshot_path, max_size=720)
        human_content = [
            {"type": "text",
             "text": f"Mode: Vision navigation (screenshot only; no DOM list).\nUser goal: {state['user_query']}\n{history_text}"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

    human_msg = HumanMessage(content=human_content)

    print(f"[AgentA] Calling Navigator in mode={mode}...")
    try:
        result = llm.invoke([system_msg, human_msg])
    except Exception as e:
        print(f"[AgentA] Model call failed: {e}")
        raise

    content = result.content

    # Flatten OpenAI-style mixed content into a single string
    if isinstance(content, str):
        raw_text = content.strip()
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        raw_text = "\n".join(parts).strip()
    else:
        raw_text = str(content)

    instruction_for_b = raw_text
    plan_steps = None
    done = False

    # Try to parse JSON as top-level Navigator response
    try:
        # Handle markdown code blocks
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        parsed = json.loads(raw_text)

        if isinstance(parsed, dict):
            # Navigator schema: instruction / reason / done / plan_steps
            instruction_for_b = parsed.get(
                "instruction", "").strip() or raw_text
            plan_steps = parsed.get("plan_steps")
            done = bool(parsed.get("done", False))
        else:
            # Not a dict → treat whole text as free-form instruction
            instruction_for_b = raw_text
            plan_steps = None
    except Exception:
        # Not JSON → free-form
        instruction_for_b = raw_text
        plan_steps = None
        done = "goal completed" in raw_text.lower()

    state["instruction"] = instruction_for_b
    state["plan_steps"] = plan_steps
    state["done"] = done
    if done:
        state["completion_via"] = state.get(
            "completion_via") or "navigator_done_signal"
        print("[Planner] Navigator marked goal completed from model response.")

    plan_flag = "present" if plan_steps is not None else "none"
    instr_preview = instruction_for_b if len(
        instruction_for_b) <= 220 else instruction_for_b[:217] + "..."
    print(
        f"[AgentA] Navigator response: done={done} plan_steps={plan_flag} instruction='{instr_preview}'")
    return state
