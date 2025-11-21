from typing import Optional


def accessible_name(el) -> str:
    """Best-effort accessible name: aria-label -> title -> aria-labelledby -> inner_text."""
    for attr in ("aria-label", "title"):
        val = el.get_attribute(attr)
        if val:
            return val.strip()

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

    try:
        txt = el.inner_text().strip()
        if txt:
            return txt
    except Exception:
        pass

    return ""


def nearest_landmark(el) -> Optional[str]:
    """Find nearest ancestor landmark (implicit or explicit)."""
    implicit = {
        "main": "main",
        "nav": "navigation",
        "aside": "complementary",
        "header": "banner",
        "footer": "contentinfo",
        "section": "region",
    }
    explicit_roles = ["main", "region", "navigation", "complementary", "banner", "contentinfo"]

    for role in explicit_roles:
        try:
            xpath = f"xpath=ancestor::*[@role='{role}']"
            anc = el.locator(xpath)
            if anc.count() > 0:
                return role
        except Exception:
            continue

    for tag, role in implicit.items():
        try:
            xpath = f"xpath=ancestor::{tag}"
            anc = el.locator(xpath)
            if anc.count() > 0:
                return role
        except Exception:
            continue

    return None

