import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from .config import OUT_DIR, PROFILE_DIR, TEAM_URL
from .elements import collect_clickable_elements
from .types import AgentAState


def capture_ui(state: AgentAState) -> AgentAState:
    """Playwright step: open Linear, capture screenshot + elements."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[AgentA] Launching Playwright and loading page...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            slow_mo=150,
        )
        page = context.new_page()

        page.goto(TEAM_URL)
        page.wait_for_timeout(4000)  # allow more time for the UI to settle

        raw_screenshot = OUT_DIR / "raw.png"
        page.screenshot(path=str(raw_screenshot), full_page=True)
        print(f"[AgentA] Screenshot captured at {raw_screenshot}")

        elements = collect_clickable_elements(page)
        print(f"[AgentA] Collected {len(elements)} elements")

        meta_path = OUT_DIR / "elements.json"
        meta = {
            "url": page.url,
            "screenshot": str(raw_screenshot),
            "user_query": state["user_query"],
            "elements": elements,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        state["screenshot_path"] = str(raw_screenshot)
        state["elements"] = elements

        context.close()

    return state
