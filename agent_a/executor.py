import json
import time
from pathlib import Path
from typing import Any, Dict, List

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


def _safe_fill(locator, text: str, role: str = ""):
    # Fail fast if role is clearly not fillable
    if role and role in ("button", "link", "tab", "menuitem", "switch"):
        raise RuntimeError(f"Cannot fill element with role '{role}'")

    try:
        if locator.count() > 1:
            locator = locator.nth(0)
    except Exception:
        pass
    locator.wait_for(state="visible", timeout=5000)
    
    # Check if editable
    try:
        is_editable = locator.is_editable(timeout=1000)
        if not is_editable:
             # Try to click first, sometimes that makes it editable
            locator.click(timeout=1000)
            is_editable = locator.is_editable(timeout=1000)
            if not is_editable:
                raise RuntimeError(f"Element is not editable (role={role})")
    except Exception:
        # If check fails, proceed with caution (might be contenteditable div)
        pass

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
    """Resolve ids -> snippets, run requested actions, take after screenshot."""
    actions: List[Dict[str, Any]] = state.get("actions") or []
    if not actions:
        print("[Executor] No actions to execute (no-op).")
        return state

    run_dir = Path(state["run_dir"])
    meta_path = run_dir / "elements.json"
    if not meta_path.exists():
        raise RuntimeError(f"Metadata file missing: {meta_path}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    page = state.get("page")
    context = state.get("context")
    if page is None or context is None:
        raise RuntimeError("No live page/context found in state for execution.")

    for idx, plan in enumerate(actions, start=1):
        target_id = plan.get("target_id")
        action = plan.get("action")
        params = plan.get("params") or {}
        if not target_id or not action:
            raise RuntimeError(f"Invalid action plan at index {idx}: {plan}")

        elem = _resolve_element(meta, target_id)
        snippet = elem.get("playwright_snippet")
        if not snippet:
            raise RuntimeError(f"No snippet for element id {target_id}")

        print(f"[Executor] Action {idx}/{len(actions)}: {action} on id={target_id} name={elem.get('name')}")

        locator = _get_locator(page, snippet)

        start = time.time()
        try:
            if action == "click":
                _safe_click(locator)
            elif action == "fill":
                text = params.get("text") or params.get("value") or ""
                if not text:
                    raise RuntimeError("Fill action missing text param")
                _safe_fill(locator, text, role=elem.get("role"))
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
        except Exception as e:
            duration = time.time() - start
            print(f"[Executor] Action failed (skipping) in {duration:.2f}s: {e}")
            continue

    after_path = run_dir / "after_action.png"
    page.screenshot(path=str(after_path), full_page=True)
    print(f"[Executor] After-action screenshot: {after_path}")

    # Browser stays open for the next step in the loop
    state["after_screenshot"] = str(after_path)
    return state
