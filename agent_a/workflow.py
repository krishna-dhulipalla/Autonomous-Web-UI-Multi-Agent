import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from .config import OUT_DIR, PROFILE_DIR, TEAM_URL, TOP_K
from .elements import collect_clickable_elements, select_top_elements
from .imaging import draw_ids_on_image
from .types import AgentAState


def capture_ui(state: AgentAState) -> AgentAState:
    """Playwright step: open Linear, capture screenshot + elements + top-K."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            slow_mo=150,
        )
        page = context.new_page()

        page.goto(TEAM_URL)
        page.wait_for_timeout(2000)

        raw_screenshot = OUT_DIR / "raw.png"
        page.screenshot(path=str(raw_screenshot), full_page=True)

        elements = collect_clickable_elements(page)
        top_elements = select_top_elements(elements, state["goal"], TOP_K)
        selected_ids = [e["id"] for e in elements if e.get("selected_for_agent")]

        meta_path = OUT_DIR / "elements.json"
        meta = {
            "url": page.url,
            "screenshot": str(raw_screenshot),
            "goal_hint": state["goal"],
            "top_k": TOP_K,
            "selected_ids": selected_ids,
            "elements": elements,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        annotated_path = draw_ids_on_image(raw_screenshot, elements, draw_only_selected=True)

        state["screenshot_path"] = str(raw_screenshot)
        state["annotated_path"] = str(annotated_path)
        state["elements"] = elements
        state["top_elements"] = top_elements

        context.close()

    return state

