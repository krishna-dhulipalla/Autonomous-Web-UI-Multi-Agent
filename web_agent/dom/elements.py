from typing import Any, Dict, List, Optional

from .accessibility import accessible_name, nearest_landmark
from ..core.config import CLICKABLE_ROLES


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
            placeholder = el.get_attribute("placeholder") or ""
            
            value = ""
            if role in ("textbox", "textarea", "searchbox", "combobox"):
                try:
                    value = el.input_value()
                except Exception:
                    pass

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
                    "placeholder": placeholder,
                    "value": value,
                    "bounding_box": box,
                    "playwright_snippet": snippet,
                    "name_hint": name_hint,
                }
            )

    # Collect contenteditable elements (often rich text editors)
    try:
        # Avoid duplicates if they have a role
        ce_loc = page.locator('[contenteditable]:not([role])')
        ce_count = ce_loc.count()
        for i in range(ce_count):
            el = ce_loc.nth(i)
            if not el.is_visible():
                continue
            box = el.bounding_box()
            if not box or (box["width"] * box["height"] < 50):
                continue

            name = accessible_name(el)
            landmark = nearest_landmark(el)
            placeholder = el.get_attribute("placeholder") or ""
            
            value = ""
            try:
                value = el.evaluate("el => el.innerText || el.textContent || ''")
            except Exception:
                pass

            elem_id = str(idx)
            idx += 1

            snippet = f"page.locator('[contenteditable]').nth({i})"

            elements.append({
                "id": elem_id,
                "role": "contenteditable",
                "name": name,
                "landmark": landmark,
                "placeholder": placeholder,
                "value": value,
                "bounding_box": box,
                "playwright_snippet": snippet,
                "name_hint": name[:30] or "ContentEditable",
            })
    except Exception:
        pass

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
                role_prio = 1 if x["role"] in (
                    "button", "textbox", "combobox") else 0
                return (has_name, name_len, role_prio)

            group.sort(key=sort_key, reverse=True)
            unique_elements.append(group[0])

    # Re-index IDs to be continuous after filtering
    for i, e in enumerate(unique_elements):
        e["id"] = str(i)

    return unique_elements
