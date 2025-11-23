from pathlib import Path

# Core destinations
TEAM_URL = "https://linear.app/testing-multi-agent-ui/team/TES/views/issues/new"
PROFILE_DIR = "playwright_profile"

# Output paths
OUT_DIR = Path("artifacts/agent_a_demo/")
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
