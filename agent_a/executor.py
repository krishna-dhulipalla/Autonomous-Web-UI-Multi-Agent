import json
import time
from pathlib import Path
from typing import Any, Dict

from playwright.sync_api import TimeoutError

from .types import AgentAState


def _resolve_element(meta: Dict[str, Any], target_id: str) -> Dict[str, Any]:
    # Prefer scored/top_k for speed, fallback to full elements
    for collection in (meta.get("top_k") or [], meta.get("elements") or []):
        for e in collection:
            if str(e.get("id")) == str(target_id):
                return e
    raise RuntimeError(f"Element with id {target_id} not found in metadata.")


def _get_locator(page, snippet: str):
    # snippet like "page.get_by_role(\"main\").get_by_role(\"button\", name='Create issue')"
    try:
        locator = eval(snippet, {"page": page})
        try:
            if locator.count() > 1:
                print(f"[Executor] Locator matched {locator.count()} elements; using the first.")
                locator = locator.nth(0)
        except Exception:
            pass
        return locator
    except Exception as e:
        raise RuntimeError(f"Failed to resolve locator from snippet: {snippet} ({e})")


def _safe_click(locator):
    try:
        if locator.count() > 1:
            locator = locator.nth(0)
    except Exception:
        pass
    locator.wait_for(state="visible", timeout=5000)
    locator.click(timeout=5000)


def _safe_fill(locator, text: str):
    try:
        if locator.count() > 1:
            locator = locator.nth(0)
    except Exception:
        pass
    locator.wait_for(state="visible", timeout=5000)
    try:
        locator.click(timeout=5000)
        locator.fill(text, timeout=5000)
    except Exception:
        # fallback to inner paragraph if it's a rich editor
        p = locator.locator("p")
        if p.count() > 0:
            p.first.click(timeout=5000)
            p.first.fill(text, timeout=5000)
        else:
            raise


def _safe_select(page, locator, option: str):
    try:
        if locator.count() > 1:
            locator = locator.nth(0)
    except Exception:
        pass
    locator.wait_for(state="visible", timeout=5000)
    locator.click(timeout=5000)
    page.get_by_role("option", name=option).click(timeout=5000)


def execute_plan(state: AgentAState) -> AgentAState:
    """Resolve id -> snippet, run the requested action, take after screenshot."""
    plan = state.get("action_plan") or {}
    target_id = plan.get("target_id")
    action = plan.get("action")
    params = plan.get("params") or {}

    if not target_id or not action:
        raise RuntimeError(f"Invalid action plan: {plan}")

    run_dir = Path(state["run_dir"])
    meta_path = run_dir / "elements.json"
    if not meta_path.exists():
        raise RuntimeError(f"Metadata file missing: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    elem = _resolve_element(meta, target_id)
    snippet = elem.get("playwright_snippet")
    if not snippet:
        raise RuntimeError(f"No snippet for element id {target_id}")

    print(f"[Executor] Action: {action} on id={target_id} name={elem.get('name')}")

    page = state.get("page")
    context = state.get("context")
    if page is None or context is None:
        raise RuntimeError("No live page/context found in state for execution.")

    locator = _get_locator(page, snippet)

    start = time.time()
    try:
        if action == "click":
            _safe_click(locator)
        elif action == "fill":
            text = params.get("text") or params.get("value") or ""
            if not text:
                raise RuntimeError("Fill action missing text param")
            _safe_fill(locator, text)
        elif action == "select":
            option = params.get("option") or params.get("value")
            if not option:
                raise RuntimeError("Select action missing option param")
            _safe_select(page, locator, option)
        elif action == "press":
            key = params.get("key") or params.get("keys")
            if not key:
                raise RuntimeError("Press action missing key param")
            locator.press(key, timeout=5000)
        else:
            raise RuntimeError(f"Unknown action type: {action}")
        page.wait_for_timeout(300)
        duration = time.time() - start
        print(f"[Executor] Action succeeded in {duration:.2f}s")
    except TimeoutError as e:
        print(f"[Executor] Timeout on action {action}: {e}")
        raise

    after_path = run_dir / "after_action.png"
    page.screenshot(path=str(after_path), full_page=True)
    print(f"[Executor] After-action screenshot: {after_path}")

    # Keep browser open for inspection until user closes
    input("[Executor] Press Enter to close the browser...")
    context.close()
    if state.get("playwright"):
        try:
            state["playwright"].stop()
        except Exception:
            pass

    state["after_screenshot"] = str(after_path)
    return state
