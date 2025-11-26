import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
                print(
                    f"[Executor] Locator matched {locator.count()} elements; using the first.")
                locator = locator.nth(0)
        except Exception:
            pass
        return locator
    except Exception as e:
        raise RuntimeError(
            f"Failed to resolve locator from snippet: {snippet} ({e})")


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


def _value_matches(locator, target_text: str) -> bool:
    """Best-effort check if control already reflects the target value."""
    tgt = (target_text or "").strip().lower()
    if not tgt:
        return False
    try:
        val = locator.input_value(timeout=500)
        if tgt in (val or "").strip().lower():
            return True
    except Exception:
        pass
    try:
        aria = locator.get_attribute("aria-label")
        if aria and tgt in aria.lower():
            return True
    except Exception:
        pass
    try:
        txt = locator.inner_text(timeout=500)
        if txt and tgt in txt.strip().lower():
            return True
    except Exception:
        pass
    return False


def _is_target_covered(page, locator) -> bool:
    """Lightweight hit-test to see if the target center is covered by another element."""
    try:
        box = locator.bounding_box(timeout=1000)
        if not box:
            return False
        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2
        handle = locator.element_handle(timeout=1000)
        if not handle:
            return False
        return page.evaluate(
            "(x, y, target) => { const el = document.elementFromPoint(x, y); return !!(el && el !== target && !target.contains(el)); }",
            center_x,
            center_y,
            handle,
        )
    except Exception:
        return False


def _dismiss_overlays_for_target(page, locator=None, target_open: bool = False) -> None:
    """
    Dismiss generic backdrops only when they are unrelated to the target.
    Skip dismissal if the target is already expanded (avoid closing its own menu).
    """
    if target_open:
        return
    try:
        backdrop = page.locator("[data-animated-popover-backdrop]").first
        if backdrop.count() and backdrop.is_visible():
            page.keyboard.press("Escape")
            try:
                backdrop.wait_for(state="detached", timeout=800)
            except Exception:
                pass
            page.wait_for_timeout(150)
    except Exception:
        pass


def _dismiss_overlays(page) -> None:
    """Backward-compatible wrapper to clear generic overlays."""
    _dismiss_overlays_for_target(page, None, target_open=False)


def _extract_form_expectations(state: AgentAState) -> Dict[str, str]:
    expectations: Dict[str, str] = {}
    plan = state.get("plan_steps") or {}
    fields = plan.get("fields") if isinstance(plan, dict) else []
    for f in fields or []:
        label = (f.get("label") or "").lower()
        val = f.get("value") or f.get("option") or ""
        if not val:
            continue
        if "title" in label:
            expectations["title"] = val
        elif "description" in label:
            expectations["description"] = val
        elif "priority" in label:
            expectations["priority"] = val
        elif "assignee" in label:
            expectations["assignee"] = val
        elif "label" in label:
            expectations["labels"] = val
    return expectations


def _dom_confirm_issue(page, expectations: Dict[str, str]) -> bool:
    """Lightweight DOM check that expected values are visible on the page."""
    if not expectations:
        return False
    try:
        for val in expectations.values():
            locator = page.locator(f"text={val}").first
            if not locator.count():
                return False
            if not locator.is_visible(timeout=1500):
                return False
        return True
    except Exception:
        return False


def _safe_select(page, locator, option: str, role: str = "", target_name: str = "") -> bool:
    """Simple, best-effort combobox select.

    This intentionally keeps logic minimal and fast:
    - Try to skip if the value already appears to be set.
    - Click the combobox to open it.
    - Click the option by its visible text.
    - Do not perform heavy verification; DOM confirmation later is the source of truth.

    Returns True if we managed to run the sequence without a hard error.
    """
    option = option or ""
    target_name = target_name or ""

    # Prefer the first match if locator resolves to multiple elements.
    try:
        if locator.count() > 1:
            locator = locator.nth(0)
    except Exception:
        pass

    # Cheap idempotency check: if it already looks like the desired value, skip work.
    try:
        if _value_matches(locator, option):
            print(
                f"[Executor] Select skipped; '{option}' already set for '{target_name}'.")
            return True
    except Exception:
        pass

    # Make sure the combobox is visible, but fail fast if not.
    try:
        locator.wait_for(state="visible", timeout=2000)
    except Exception as e:
        raise RuntimeError(
            f"Select combobox not visible for '{target_name}': {e}")

    # Open the combobox.
    try:
        locator.click(timeout=2000)
    except Exception as e:
        raise RuntimeError(
            f"Select failed to open combobox for '{target_name}': {e}")

    # Best-effort: click the option by its text.
    try:
        option_locator = page.locator(f"text={option}").first
        option_locator.wait_for(state="visible", timeout=2000)
        option_locator.click(timeout=2000)
    except Exception as e:
        # We log but do not do heavy recovery here; DOM confirmation will judge success.
        print(
            f"[Executor] Option click best-effort failed for '{option}' on '{target_name}': {e}")
        return False

    # Small settle to let the UI update.
    try:
        page.wait_for_timeout(150)
    except Exception:
        pass

    return True


def execute_plan(state: AgentAState) -> AgentAState:
    """Resolve ids -> snippets, run requested actions, take after screenshot."""
    actions: List[Dict[str, Any]] = state.get("actions") or []
    if not actions:
        print("[Executor] No actions to execute (no-op).")
        return state
    step_start = time.time()
    slowest_action = ("", 0.0)
    failure_notes: List[str] = []

    run_dir = Path(state["run_dir"])
    # Use in-memory elements/top_k instead of reading elements.json
    meta = {
        "elements": state.get("elements") or [],
        "top_k": state.get("top_elements") or [],
    }
    page = state.get("page")
    context = state.get("context")
    if page is None or context is None:
        raise RuntimeError(
            "No live page/context found in state for execution.")

    executed_ids = []
    for idx, plan in enumerate(actions, start=1):
        if time.time() - step_start > 20:
            failure_notes.append(
                "Executor step budget (20s) exceeded; remaining actions skipped.")
            print("[Executor] Step time budget exceeded; skipping remaining actions.")
            break
        target_id = plan.get("target_id")
        action = plan.get("action")
        params = plan.get("params") or {}
        if not target_id or not action:
            raise RuntimeError(f"Invalid action plan at index {idx}: {plan}")

        elem = _resolve_element(meta, target_id)
        snippet = elem.get("playwright_snippet")
        if not snippet:
            raise RuntimeError(f"No snippet for element id {target_id}")

        print(
            f"[Executor] Step={state.get('step', 0)} Action {idx}/{len(actions)}: {action} on id={target_id} name={elem.get('name')}")

        locator = _get_locator(page, snippet)
        role = (elem.get("role") or "").lower()

        start = time.time()
        try:
            if action == "click":
                # Only clear overlays for "global" actions, not menu options
                if role in {"button", "link", "tab"}:
                    _dismiss_overlays(page)

                _safe_click(locator)
            elif action == "fill":
                text = params.get("text") or params.get("value") or ""
                if not text:
                    raise RuntimeError("Fill action missing text param")
                _safe_fill(locator, text, role=elem.get("role"))
            elif action == "select":
                option = params.get("option")
                if not option:
                    print(
                        f"[Executor] Missing option for select action on {target_id}")
                    continue
                # Guard: only select on dropdown-like roles
                if (elem.get("role") or "") not in {"combobox", "menuitem"}:
                    print(
                        f"[Executor] Skipping select on non-select role {elem.get('role')} for {target_id}"
                    )
                    continue
                # Basic value compatibility check: avoid feeding date-ish values into non-date controls
                opt_lower = option.lower()
                if "status" in (elem.get("name") or "").lower() and opt_lower in [
                    "today",
                    "tomorrow",
                    "next week",
                    "next day",
                    "next month",
                ]:
                    print(
                        f"[Executor] Skipping select on status-like control with date-like option '{option}'"
                    )
                    continue

                ok = _safe_select(
                    page,
                    locator,
                    option,
                    role=elem.get("role"),
                    target_name=elem.get("name"),
                )
                if not ok:
                    # Fast failure: log and let the outer try/except mark this action as failed.
                    raise RuntimeError(
                        f"Select best-effort failed for '{option}' on '{elem.get('name')}'"
                    )
            elif action == "press":
                key = params.get("key") or params.get("keys")
                if not key:
                    raise RuntimeError("Press action missing key param")
                locator.press(key, timeout=5000)
            else:
                raise RuntimeError(f"Unknown action type: {action}")
            page.wait_for_timeout(300)
            duration = time.time() - start
            if duration > slowest_action[1]:
                slowest_action = (f"{action} {target_id}", duration)
            print(f"[Executor] Action succeeded in {duration:.2f}s")
            executed_ids.append(target_id)
        except Exception as e:
            duration = time.time() - start
            print(
                f"[Executor] Action failed (skipping) in {duration:.2f}s: {e}")
            failure_notes.append(
                f"{action} failed on '{elem.get('name')}' ({e})")
            continue

    total_duration = time.time() - step_start
    print(
        f"[Executor] Step timing: total={total_duration:.2f}s slowest={slowest_action[0]} ({slowest_action[1]:.2f}s)")

    # Capture after-action screenshot
    after_path = run_dir / "after_action.png"
    page.screenshot(path=str(after_path), full_page=True)
    print(f"[Executor] After-action screenshot: {after_path}")

    # Basic DOM confirmation for form submissions
    expectations = _extract_form_expectations(state)
    if expectations and _dom_confirm_issue(page, expectations):
        print("[Executor] DOM confirmation passed; marking goal done.")
        state["done"] = True
        state["completion_via"] = state.get(
            "completion_via") or "dom_confirmation"

    # Compute hash for UI change detection
    try:
        from PIL import Image
        import io

        # We can read the file we just wrote, or get bytes directly.
        # Reading file is safer to ensure it exists.
        img_bytes = after_path.read_bytes()

        def _compute_dhash(image_bytes):
            try:
                img = Image.open(io.BytesIO(image_bytes)).convert(
                    "L").resize((9, 8), Image.Resampling.LANCZOS)
                pixels = list(img.getdata())
                diff = []
                for row in range(8):
                    for col in range(8):
                        diff.append(pixels[row * 9 + col] >
                                    pixels[row * 9 + col + 1])
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
            ineffective = set(state.get("ineffective_targets") or [])
            ineffective.update([tid for tid in executed_ids if tid])
            state["ineffective_targets"] = list(ineffective)
        else:
            state["no_change_steps"] = 0
            state["ineffective_targets"] = []

        state["last_step_succeeded"] = not ui_same
        if "tried_ids" not in state:
            state["tried_ids"] = []
        state["tried_ids"].extend([tid for tid in executed_ids if tid])

    except Exception as e:
        print(f"[Executor] UI detection failed: {e}")
        state["ui_same"] = False

    # Browser stays open for the next step in the loop
    state["after_screenshot"] = str(after_path)
    if failure_notes:
        hint = "; ".join(failure_notes)
        existing_hint = state.get("followup_hint") or ""
        state["followup_hint"] = (existing_hint + " " + hint).strip()

    return state
