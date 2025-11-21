from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


class AgentAState(TypedDict):
    goal: str
    screenshot_path: Optional[str]
    annotated_path: Optional[str]
    elements: List[Dict[str, Any]]
    top_elements: List[Dict[str, Any]]
    chosen_id: Optional[str]
    reason: Optional[str]


class AgentAOutput(BaseModel):
    chosen_id: str = Field(description="The id of the UI element to act on")
    reason: str = Field(description="Short explanation of why this id was chosen")

