from typing import Any, Dict, List, Optional, TypedDict


class AgentAState(TypedDict):
    run_id: str
    run_dir: str
    user_query: str
    history: Optional[List[str]]
    last_actions: Optional[List[Dict[str, Any]]]
    ineffective_targets: Optional[List[str]]
    planning_mode: Optional[str]
    maybe_done: Optional[bool]
    screenshot_path: Optional[str]
    elements: List[Dict[str, Any]]
    instruction: Optional[str]
    plan_steps: Optional[Any]
    tried_ids: Optional[List[str]]
    top_elements: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    followup_hint: Optional[str]
    after_screenshot: Optional[str]
    # Live browser handles (kept in-memory for single-run)
    playwright: Any
    context: Any
    page: Any
    step: int
    done: bool
    
    # DOM-First Planning State
    planning_mode: Optional[str]  # "vision" | "dom"
    last_planning_mode: Optional[str]
    dom_attempts_on_this_screen: int
    last_step_succeeded: bool
    step_index: int
    
    # Dataset
    dataset_path: Optional[str]
