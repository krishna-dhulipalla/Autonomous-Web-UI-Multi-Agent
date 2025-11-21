from typing import Any, Dict, List, Optional, TypedDict


class AgentAState(TypedDict):
    user_query: str
    history: Optional[List[str]]
    screenshot_path: Optional[str]
    elements: List[Dict[str, Any]]
    instruction: Optional[str]
