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
    
    # Check for completion
    plan_steps = state.get("plan_steps")
    instruction = state.get("instruction", "")
    
    done = False
    if plan_steps and isinstance(plan_steps, dict) and plan_steps.get("done"):
        done = True
        print(f"[AgentA] Goal completed at step {step} (via plan_steps).")
    elif "goal completed" in instruction.lower():
        done = True
        print(f"[AgentA] Goal completed at step {step} (via instruction).")
    elif step >= MAX_STEPS:
        done = True
        print(f"[AgentA] Max steps ({MAX_STEPS}) reached.")
        
    state["done"] = done
    
    # Update history
    actions = state.get("actions", [])
    action_summary = ", ".join([f"{a.get('action')} {a.get('target_id')}" for a in actions])
    followup_hint = state.get("followup_hint") or ""
    history_entry = f"Step {step}: Instr='{instruction}' Actions=[{action_summary}] Followup='{followup_hint}'"
    
    history = state.get("history", [])
    history.append(history_entry)
    
    # Rolling window: keep last 5
    if len(history) > 5:
        history = history[-5:]
    state["history"] = history
    
    # Clear per-step fields for next iteration
    if not done:
        state["instruction"] = None
        state["plan_steps"] = None
        state["elements"] = []
        state["top_elements"] = []
        state["actions"] = []
        state["followup_hint"] = None
        # screenshot_path will be overwritten by capture_ui
        
    return state
