import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..core.types import AgentAState
from ..utils.imaging import image_to_data_url


def agent_a(state: AgentAState) -> AgentAState:
    """Vision LLM: take user query + raw screenshot, return one textual instruction."""
    if not state.get("screenshot_path"):
        raise RuntimeError("No screenshot available for Agent A.")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1,
                     timeout=45, max_retries=1)

    screenshot_path = Path(state["screenshot_path"])
    data_url = image_to_data_url(screenshot_path, max_size=960)

    system_msg = SystemMessage(
        content=(
            "You are **Navigator**, a high-level planning agent that guides another agent (Agent B) to operate arbitrary web applications.\n"
            "\n"
            "You see:\n"
            "- The user's overall goal\n"
            "- The current UI screenshot\n"
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
            "5. Detect when the goal is completed.\n"
            "   - If the UI clearly shows that the requested task is already done, mark the goal as complete.\n"
            "\n"
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

    human_content = [
        {"type": "text",
            "text": f"User goal: {state['user_query']}\n{history_text}"},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    human_msg = HumanMessage(content=human_content)

    print("[AgentA] Calling vision model with screenshot and user query...")
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

    print(f"[AgentA] Model returned raw: {raw_text}")
    print(f"[AgentA] Parsed instruction: {instruction_for_b}")
    print(
        f"[AgentA] Parsed done={done}, has plan_steps={plan_steps is not None}")
    return state
