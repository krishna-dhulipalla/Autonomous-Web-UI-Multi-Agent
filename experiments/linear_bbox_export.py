import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

TEAM_URL = "https://linear.app/testing-multi-agent-ui/team/TES/views/issues/new"
PROFILE_DIR = "playwright_profile"

OUT_DIR = Path("artifacts/linear_bbox/test_scored")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Optional: high-level goal to bias scores (can be "" or None)
GOAL_HINT: Optional[str] = "create new issue"  # change per demo if you like
TOP_K = 25  # how many elements to keep for Agent A / annotated image


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


# -----------------------------------------------------------
# ACCESSIBLE NAME (fixed)
# -----------------------------------------------------------
def accessible_name(el) -> str:
    """Best-effort accessible name: aria-label -> title -> aria-labelledby -> inner_text."""

    # Strong semantic attributes
    for attr in ("aria-label", "title"):
        val = el.get_attribute(attr)
        if val:
            return val.strip()

    # aria-labelledby may contain multiple ids separated by spaces
    labelled_by = el.get_attribute("aria-labelledby")
    if labelled_by:
        for id_ in labelled_by.split():
            try:
                labelled_el = el.page.locator(f"#{id_}")
                if labelled_el.count() > 0:
                    txt = labelled_el.first.inner_text().strip()
                    if txt:
                        return txt
            except Exception:
                continue

    # fallback: direct inner text
    try:
        txt = el.inner_text().strip()
        if txt:
            return txt
    except Exception:
        pass

    return ""


# -----------------------------------------------------------
# LANDMARK DETECTOR (fixed)
# Handles implicit landmark tags (<main>, <nav>, <aside>, ...)
# -----------------------------------------------------------
def nearest_landmark(el) -> Optional[str]:
    """Find nearest ancestor landmark (implicit or explicit)."""

    # implicit landmark HTML tags → landmark roles
    implicit = {
        "main": "main",
        "nav": "navigation",
        "aside": "complementary",
        "header": "banner",
        "footer": "contentinfo",
        "section": "region",
    }

    # explicit ARIA landmark roles
    explicit_roles = ["main", "region", "navigation",
                      "complementary", "banner", "contentinfo"]

    # 1. Try explicit roles (role="main")
    for role in explicit_roles:
        try:
            xpath = f"xpath=ancestor::*[@role='{role}']"
            anc = el.locator(xpath)
            if anc.count() > 0:
                return role
        except Exception:
            continue

    # 2. Try implicit semantic tags (<main>, <nav>, etc.)
    for tag, role in implicit.items():
        try:
            xpath = f"xpath=ancestor::{tag}"
            anc = el.locator(xpath)
            if anc.count() > 0:
                return role
        except Exception:
            continue

    return None


# -----------------------------------------------------------
# COLLECT CLICKABLE ELEMENTS
# -----------------------------------------------------------
def collect_clickable_elements(page) -> List[Dict[str, Any]]:
    elements: List[Dict[str, Any]] = []
    idx = 0

    for role in CLICKABLE_ROLES:
        loc = page.get_by_role(role)
        count = loc.count()

        for i in range(count):
            el = loc.nth(i)

            # Must be visible
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue

            # Must have bounding box
            box = el.bounding_box()
            if not box:
                continue

            # Remove tiny noise elements
            area = box["width"] * box["height"]
            if area < 50:
                continue

            name = accessible_name(el)
            landmark = nearest_landmark(el)

            elem_id = str(idx)
            idx += 1

            name_hint = (name[:30] + "...") if len(name) > 30 else name

            # Build safe Playwright snippet
            locator_call = (
                f'get_by_role("{role}", name={name!r})'
                if name
                else f'get_by_role("{role}")'
            )

            if landmark:
                snippet = f'page.get_by_role("{landmark}").{locator_call}'
            else:
                snippet = f"page.{locator_call}"

            elements.append(
                {
                    "id": elem_id,
                    "role": role,
                    "name": name,
                    "landmark": landmark,
                    "bounding_box": box,
                    "playwright_snippet": snippet,
                    "name_hint": name_hint,
                }
            )

    return elements


# -----------------------------------------------------------
# SCORING
# -----------------------------------------------------------
def score_element(elem: Dict[str, Any], goal_hint: Optional[str]) -> float:
    """Heuristic score for how important this element is for the agent."""
    score = 0.0

    role = elem["role"]
    name = (elem.get("name") or "").lower()
    box = elem["bounding_box"]
    area = box["width"] * box["height"]

    # 1) Role importance
    if role == "button":
        score += 3.0
    elif role in ("link", "combobox", "textbox"):
        score += 2.0
    else:
        score += 1.0

    # 2) Has readable name
    if name:
        score += 0.5

    # 3) Generic keywords that often matter in Linear
    keywords = ["issue", "import", "filter", "new", "create", "view", "add"]
    for kw in keywords:
        if kw in name:
            score += 1.5

    # 4) Goal hint overlap (very cheap, not full semantic search)
    if goal_hint:
        gh = goal_hint.lower()
        for tok in set(gh.split()):
            if tok and tok in name:
                score += 2.0

    # 5) Size preference: reward medium-ish clickable areas
    if 500 <= area <= 25000:
        score += 1.0

    # 6) Landmark preference: main content usually more relevant
    if elem.get("landmark") == "main":
        score += 1.0

    return score


def select_top_elements(
    elements: List[Dict[str, Any]], goal_hint: Optional[str], top_k: int
) -> List[Dict[str, Any]]:
    """Compute scores, mark selected_for_agent, and return top_k subset."""
    for e in elements:
        e["score"] = score_element(e, goal_hint)
        e["selected_for_agent"] = False

    sorted_elems = sorted(elements, key=lambda e: e["score"], reverse=True)

    for e in sorted_elems[:top_k]:
        e["selected_for_agent"] = True

    return sorted_elems[:top_k]


# -----------------------------------------------------------
# DRAW BOUNDING BOXES ON SCREENSHOT
# -----------------------------------------------------------
def draw_bboxes_on_image(
    screenshot_path: Path,
    elements: List[Dict[str, Any]],
    draw_only_selected: bool = True,
) -> Path:
    """Overlay bounding boxes with element ids on the screenshot."""
    img = Image.open(screenshot_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for elem in elements:
        if draw_only_selected and not elem.get("selected_for_agent", False):
            continue

        box = elem["bounding_box"]
        elem_id = elem["id"]

        x = int(box["x"])
        y = int(box["y"])
        w = int(box["width"])
        h = int(box["height"])

        draw.rectangle([x, y, x + w, y + h], outline=(255, 0, 0), width=2)

        label = f"{elem_id} {elem.get('name_hint', '')}".strip()
        text_pos = (x + 2, y + 2)
        draw.text(text_pos, label, fill=(255, 0, 0), font=font)

    annotated_path = OUT_DIR / "step_01_annotated.png"
    img.save(annotated_path)
    return annotated_path


# -----------------------------------------------------------
# MAIN RUN
# -----------------------------------------------------------
def run():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR,
            headless=False,
            slow_mo=150,
        )
        page = context.new_page()

        # If it's your first run, login once; later runs will reuse session
        # page.goto("https://linear.app/")
        # print("dY`% If needed, log in to Linear in the browser window.")
        # input("Press Enter to continue to team board... ")

        page.goto(TEAM_URL)
        page.wait_for_timeout(2000)

        # 1) Raw screenshot
        raw_screenshot = OUT_DIR / "step_01_raw.png"
        page.screenshot(path=str(raw_screenshot), full_page=True)
        print(f"📸 Raw screenshot saved → {raw_screenshot}")

        # 2) Collect clickable elements
        print("🔍 Collecting clickable elements...")
        elements = collect_clickable_elements(page)
        print(f"   Found {len(elements)} clickable elements")

        # 3) Score + select top-K for agent view
        top_elements = select_top_elements(elements, GOAL_HINT, TOP_K)
        selected_ids = [e["id"]
                        for e in elements if e.get("selected_for_agent")]

        print(
            f"   Selected {len(selected_ids)} elements for agent view (TOP_K={TOP_K})")

        # 4) Save metadata JSON (all elements, with scores & selected flag)
        meta_path = OUT_DIR / "step_01_elements.json"
        meta = {
            "url": page.url,
            "screenshot": str(raw_screenshot),
            "goal_hint": GOAL_HINT,
            "top_k": TOP_K,
            "selected_ids": selected_ids,
            "elements": elements,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"🧾 Metadata saved → {meta_path}")

        # 5) Draw bounding boxes only for selected elements
        annotated_path = draw_bboxes_on_image(
            raw_screenshot, elements, draw_only_selected=True)
        print(f"🖼 Annotated screenshot (selected only) → {annotated_path}")

        input("\nPress Enter to exit… (browser stays open)")


if __name__ == "__main__":
    run()
