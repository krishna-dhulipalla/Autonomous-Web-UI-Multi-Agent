import json
import time
from pathlib import Path
from typing import Any, Dict, List

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
    
    # Click to open dropdown
    locator.click(timeout=5000)
    
    # Attempt 1: Standard role="option"
    try:
        page.get_by_role("option", name=option).click(timeout=3000)
        return
    except Exception:
        print(f"[Executor] Standard select failed for '{option}', trying text match...")

    # Attempt 2: Text match (for non-standard dropdowns)
    try:
        # Look for visible text in the dropdown area
        page.locator(f"text={option}").first.click(timeout=3000)
        return
    except Exception:
        print(f"[Executor] Text match select failed for '{option}', trying typeahead...")

    # Attempt 3: Typeahead fallback (fill + Enter)
    # This is risky if the control isn't a combobox, but we are here because select failed.
    try:
        locator.fill(option, timeout=3000)
        locator.press("Enter", timeout=3000)
    except Exception as e:
        raise RuntimeError(f"All select strategies failed for '{option}': {e}")


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
                option = params.get("option")
                if not option:
                    print(f"[Executor] Missing option for select action on {target_id}")
                    continue
                # Guard: only select on dropdown-like roles
                if (elem.get("role") or "") not in {"combobox", "menuitem"}:
                    print(f"[Executor] Skipping select on non-select role {elem.get('role')} for {target_id}")
                    continue
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

    # Capture after-action screenshot
    after_path = run_dir / "after_action.png"
    page.screenshot(path=str(after_path), full_page=True)
    print(f"[Executor] After-action screenshot: {after_path}")

    # Compute hash for UI change detection
    try:
        from PIL import Image
        import io
        
        # We can read the file we just wrote, or get bytes directly. 
        # Reading file is safer to ensure it exists.
        img_bytes = after_path.read_bytes()
        
        def _compute_dhash(image_bytes):
            try:
                img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
                pixels = list(img.getdata())
                diff = []
                for row in range(8):
                    for col in range(8):
                        diff.append(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
                return sum([1 << i for i, v in enumerate(diff) if v])
            except Exception as e:
                print(f"[Executor] dHash failed: {e}")
                return 0

        current_hash = _compute_dhash(img_bytes)
        last_hash = state.get("last_image_hash")
        
        # Compare
        ui_same = False
        if last_hash is not None and current_hash != 0:
            # Exact match or very close? dHash is robust, exact match is usually fine for "no change"
            # But let's allow a tiny bit of noise if we wanted, but for now exact match on 64-bit hash
            ui_same = (current_hash == last_hash)
            
        state["ui_same"] = ui_same
        state["last_image_hash"] = current_hash
        
        if ui_same:
            state["no_change_steps"] = state.get("no_change_steps", 0) + 1
            print(f"[Executor] UI Unchanged (hash={current_hash})")
        else:
            state["no_change_steps"] = 0
            # If changed, we might want to clear tried_ids or keep them? 
            # Usually if UI changed, we are in a new state, so previous tried_ids are less relevant 
            # UNLESS we are in a loop. But the request says "Append attempted target_ids".
            # Let's append regardless, but maybe Ranker clears them if ui_same is False? 
            # The request says: "Make Ranker... avoid repeats when UI is unchanged". 
            # So we just accumulate them here.
            
        # Track tried IDs
        executed_ids = [a.get("target_id") for a in actions if a.get("target_id")]
        if "tried_ids" not in state:
            state["tried_ids"] = []
        state["tried_ids"].extend(executed_ids)
        
    except Exception as e:
        print(f"[Executor] UI detection failed: {e}")
        state["ui_same"] = False

    # Browser stays open for the next step in the loop
    state["after_screenshot"] = str(after_path)
    return state
