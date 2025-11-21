from pathlib import Path
from typing import Optional

# Core destinations
TEAM_URL = "https://linear.app/testing-multi-agent-ui/team/TES/active"
PROFILE_DIR = "playwright_profile"

# Output paths
OUT_DIR = Path("artifacts/agent_a_demo/create_project")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Element filtering
CLICKABLE_ROLES = [
    "button",
    "link",
    "checkbox",
    "radio",
    "switch",
    "menuitem",
    "tab",
    "textbox",
    "combobox",
]

# Agent defaults
DEFAULT_GOAL_HINT: Optional[str] = "create a new project"
TOP_K = 20

