from typing import Any, Dict, List, Optional, TypedDict


class AgentAState(TypedDict):
    run_id: str
    run_dir: str
    user_query: str
    history: Optional[List[str]]
    screenshot_path: Optional[str]
    elements: List[Dict[str, Any]]
    instruction: Optional[str]
    tried_ids: Optional[List[str]]
    top_elements: List[Dict[str, Any]]
    action_plan: Optional[Dict[str, Any]]
    after_screenshot: Optional[str]
    # Live browser handles (kept in-memory for single-run)
    playwright: Any
    context: Any
    page: Any
