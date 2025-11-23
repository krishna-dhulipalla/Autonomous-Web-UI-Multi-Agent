from typing import Any, Dict, List, Optional

from .accessibility import accessible_name, nearest_landmark
from .config import CLICKABLE_ROLES


def collect_clickable_elements(page) -> List[Dict[str, Any]]:
    """Return visible clickable elements with bounding boxes and a locator hint."""
    elements: List[Dict[str, Any]] = []
    idx = 0

    for role in CLICKABLE_ROLES:
        loc = page.get_by_role(role)
        count = loc.count()

        for i in range(count):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue

            box = el.bounding_box()
            if not box:
                continue

            area = box["width"] * box["height"]
            if area < 50:
                continue

            name = accessible_name(el)
            landmark = nearest_landmark(el)

            elem_id = str(idx)
            idx += 1

            name_hint = (name[:30] + "...") if len(name) > 30 else name

            locator_call = (
                f'get_by_role("{role}", name={name!r})'
                if name
                else f'get_by_role("{role}").nth({i})'
            )
            if landmark and name:
                # Only use landmark if we have a name, otherwise nth(i) is safer globally for the role
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

    # De-duplication: Group by spatial location (rounded to nearest 2px to catch sub-pixel diffs)
    spatial_map: Dict[str, List[Dict[str, Any]]] = {}
    for e in elements:
        box = e["bounding_box"]
        # Create a spatial key
        key = f"{round(box['x'] / 2)}_{round(box['y'] / 2)}_{round(box['width'] / 2)}_{round(box['height'] / 2)}"
        if key not in spatial_map:
            spatial_map[key] = []
        spatial_map[key].append(e)

    unique_elements = []
    for key, group in spatial_map.items():
        if len(group) == 1:
            unique_elements.append(group[0])
        else:
            # Pick the best one: prefer longest name, then specific roles
            # Sort by: has_name (desc), name_len (desc), role_priority (desc)
            def sort_key(x):
                has_name = bool(x["name"])
                name_len = len(x["name"]) if x["name"] else 0
                role_prio = 1 if x["role"] in ("button", "textbox", "combobox") else 0
                return (has_name, name_len, role_prio)

            group.sort(key=sort_key, reverse=True)
            unique_elements.append(group[0])

    # Re-index IDs to be continuous after filtering
    for i, e in enumerate(unique_elements):
        e["id"] = str(i)

    return unique_elements


def score_element(elem: Dict[str, Any], goal_hint: Optional[str]) -> float:
    score = 0.0
    role = elem["role"]
    name = (elem.get("name") or "").lower()
    box = elem["bounding_box"]
    area = box["width"] * box["height"]

    if role == "button":
        score += 3.0
    elif role in ("link", "combobox", "textbox"):
        score += 2.0
    else:
        score += 1.0

    if name:
        score += 0.5

    keywords = ["issue", "import", "filter", "new", "create", "view", "add"]
    for kw in keywords:
        if kw in name:
            score += 1.5

    if goal_hint:
        gh = goal_hint.lower()
        for tok in set(gh.split()):
            if tok and tok in name:
                score += 2.0

    if 500 <= area <= 25000:
        score += 1.0

    if elem.get("landmark") == "main":
        score += 1.0

    return score


def select_top_elements(
    elements: List[Dict[str, Any]],
    goal_hint: Optional[str],
    top_k: int,
) -> List[Dict[str, Any]]:
    for e in elements:
        e["score"] = score_element(e, goal_hint)
        e["selected_for_agent"] = False

    sorted_elems = sorted(elements, key=lambda e: e["score"], reverse=True)
    for e in sorted_elems[:top_k]:
        e["selected_for_agent"] = True

    return sorted_elems[:top_k]

