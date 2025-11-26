from typing import List
from .types import AgentAState

MAX_STEPS = 15


def finalize_step(state: AgentAState) -> AgentAState:
    """
    Update step count, history, and check for completion.
    Maintains a rolling window of history (last 5 steps).
    """
    step = state.get("step", 0) + 1
    state["step"] = step
    maybe_done_flag = bool(state.get("maybe_done", False))

    # --- Completion flags ---
    plan_steps = state.get("plan_steps")
    instruction_raw = state.get("instruction")

    # Normalize instruction to a safe string
    if isinstance(instruction_raw, str):
        instruction = instruction_raw
    else:
        instruction = ""
    instr_lc = instruction.lower()

    done = bool(state.get("done"))

    # 1) If some planner ever encodes done into plan_steps (defensive)
    if isinstance(plan_steps, dict) and plan_steps.get("done"):
        done = True
        state["completion_via"] = state.get("completion_via") or "plan_steps"
        print(f"[AgentA] Goal completed at step {step} (via plan_steps).")

    # 2) String-based heuristic from Navigator ("Goal completed.")
    elif not done and "goal completed" in instr_lc:
        done = True
        state["completion_via"] = state.get("completion_via") or "navigator_instruction"
        print(f"[AgentA] Goal completed at step {step} (via instruction).")

    # 3) Safety cap
    elif step >= MAX_STEPS:
        done = True
        state["completion_via"] = state.get("completion_via") or "max_steps"
        print(f"[AgentA] Max steps ({MAX_STEPS}) reached.")

    state["done"] = done

    # --- DOM-First State Updates ---
    state["last_planning_mode"] = state.get("planning_mode")

    ui_same = state.get("ui_same", False)
    actions = state.get("actions", [])

    # Success = actions executed AND UI changed (or goal done)
    if done:
        succeeded = True
    elif not actions:
        succeeded = False  # No actions generated
    else:
        succeeded = not ui_same

    state["last_step_succeeded"] = succeeded

    if not ui_same:
        state["dom_attempts_on_this_screen"] = 0
    else:
        if state.get("planning_mode") == "dom":
            state["dom_attempts_on_this_screen"] = state.get(
                "dom_attempts_on_this_screen", 0
            ) + 1

    # --- History update ---
    actions = state.get("actions", [])
    action_summary = ", ".join(
        [f"{a.get('action')} {a.get('target_id')}" for a in actions]
    )
    followup_hint = state.get("followup_hint") or ""
    history_entry = (
        f"Step {step}: Instr='{instruction}' "
        f"Actions=[{action_summary}] "
        f"Followup='{followup_hint}'"
    )

    history = state.get("history", [])
    history.append(history_entry)

    # Rolling window: keep last 5
    if len(history) > 5:
        history = history[-5:]
    state["history"] = history

    # Log to dataset
    from .dataset import log_step
    log_step(state)

    # --- Per-step cleanup ---
    if not done:
        # Clear step-scoped fields for next iteration
        state["instruction"] = None
        state["plan_steps"] = None
        state["elements"] = []
        state["top_elements"] = []
        state["actions"] = []
        state["followup_hint"] = None
        state["last_actions"] = actions
        # Carry maybe_done signal from Agent B so the next Planner pass can verify.
        state["maybe_done"] = maybe_done_flag
    else:
        # Preserve last actions & mark maybe_done so Planner can double-check if needed
        state["last_actions"] = actions
        state["maybe_done"] = True
        # screenshot_path will be overwritten by capture_ui on next run if needed

    return state
