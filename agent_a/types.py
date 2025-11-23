from typing import Any, Dict, List, Optional, TypedDict


class AgentAState(TypedDict):
    run_id: str
    run_dir: str
    user_query: str
    history: Optional[List[str]]
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
