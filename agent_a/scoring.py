import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# Role and landmark weights
ROLE_WEIGHTS = {
    "button": 3.0,
    "link": 2.0,
    "combobox": 2.0,
    "textbox": 2.0,
    "menuitem": 1.5,
    "checkbox": 1.5,
    "radio": 1.5,
    "switch": 1.5,
    "tab": 1.5,
}

LANDMARK_WEIGHTS = {
    "main": 1.0,
    "navigation": 0.5,
    "region": 0.5,
    "complementary": 0.5,
    "banner": 0.5,
    "contentinfo": 0.5,
}

DESTRUCTIVE_TOKENS = {"delete", "remove", "discard", "close", "dismiss", "trash"}
GENERIC_GLOBAL_TOKENS = {"workspace", "search", "settings", "help", "profile", "menu"}

# Verb families (generic, not app-specific)
COMMON_ACTION_TOKENS = {
    "create": {"create", "new", "add", "start"},
    "open": {"open", "show", "view"},
    "edit": {"edit", "modify", "change"},
    "filter": {"filter", "search", "sort"},
    "navigate": {"go", "navigate", "jump", "switch"},
}

INTENT_ROLE_MAP = {
    "fill": {"textbox", "combobox"},
    "type": {"textbox"},
    "enter": {"textbox"},
    "select": {"combobox", "menuitem"},
    "choose": {"combobox", "menuitem"},
    "click": {"button", "link"},
    "create": {"button", "link"},
    "open": {"button", "link"},
}

SYNONYM_MAP = {
    "issue": {"ticket", "bug", "task"},
    "new": {"create", "add"},
    "project": {"workspace"},
    "priority": {"urgency"},
    "assignee": {"owner"},
    "filter": {"search"},
}


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9]+", text.lower()) if t]


def phrase_match(text: str, phrase: str) -> bool:
    t = text.lower()
    p = phrase.lower()
    return p in t if p else False


def token_overlap(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    set_a, set_b = set(a), set(b)
    inter = set_a & set_b
    union = set_a | set_b
    return len(inter) / len(union) if union else 0.0


def synonym_overlap(tokens: List[str]) -> float:
    score = 0.0
    token_set = set(tokens)
    for key, syns in SYNONYM_MAP.items():
        if key in token_set or token_set & syns:
            score += 1.0
    return score


def action_semantic_score(instr_tokens: set, name_tokens: set) -> float:
    s = 0.0
    for syns in COMMON_ACTION_TOKENS.values():
        if instr_tokens & syns and name_tokens & syns:
            s += 1.5
    return s


def infer_intent_role(instruction_tokens: List[str]) -> Optional[set]:
    for intent, roles in INTENT_ROLE_MAP.items():
        if intent in instruction_tokens:
            return roles
    return None


def score_element(elem: Dict, instruction: str, tried_ids: Optional[List[str]] = None) -> float:
    name = (elem.get("name") or "").strip()
    role = elem.get("role") or ""
    landmark = elem.get("landmark") or ""
    elem_id = elem.get("id") or ""

    instr_tokens = tokenize(instruction or "")
    name_tokens = tokenize(name)
    instr_tokens_set = set(instr_tokens)
    name_tokens_set = set(name_tokens)

    score = 0.0
    score += ROLE_WEIGHTS.get(role, 1.0)
    score += LANDMARK_WEIGHTS.get(landmark, 0.0)

    # Phrase match
    if phrase_match(instruction, name):
        score += 2.0

    # Token overlap
    overlap = token_overlap(instr_tokens, name_tokens)
    score += 1.5 * overlap

    # Synonym overlap
    score += 1.0 * synonym_overlap(instr_tokens + name_tokens)

    # Generic chrome penalty
    if name_tokens_set & GENERIC_GLOBAL_TOKENS:
        score -= 0.5

    # Action verb alignment
    score += action_semantic_score(instr_tokens_set, name_tokens_set)

    # Destructive penalty (if not requested)
    if any(tok in DESTRUCTIVE_TOKENS for tok in name_tokens):
        if not any(tok in DESTRUCTIVE_TOKENS for tok in instr_tokens):
            score -= 3.0

    # Intent-role alignment
    intended_roles = infer_intent_role(instr_tokens)
    if intended_roles and role in intended_roles:
        score += 1.0

    # Retry penalty
    if tried_ids and elem_id in tried_ids:
        score -= 1.5

    # Garbage name penalty
    if is_garbage_name(name):
        score -= 5.0

    return score


def is_garbage_name(name: str) -> bool:
    """Return True if name is likely garbage (e.g. '1', '123', or very short non-words)."""
    if not name:
        return False
    # Purely numeric
    if name.isdigit():
        return True
    # Very short and not a common word
    if len(name) < 3 and name.lower() not in {"ok", "go", "id", "up", "to", "at", "in", "on", "by"}:
        return True
    return False


def select_top(elements: List[Dict], instruction: str, top_k: int = 10, tried_ids: Optional[List[str]] = None):
    scored = []
    for e in elements:
        s = score_element(e, instruction, tried_ids)
        e_copy = {k: e.get(k) for k in ("id", "role", "name", "landmark", "playwright_snippet")}
        e_copy["score"] = s
        scored.append(e_copy)

    scored_sorted = sorted(scored, key=lambda x: x["score"], reverse=True)

    selected = []
    used_ids = set()

    # baseline top_k
    for e in scored_sorted:
        if len(selected) >= top_k:
            break
        selected.append(e)
        used_ids.add(e["id"])

    instr_lc = instruction.lower()
    # ensure some textboxes for fill instructions
    if any(tok in instr_lc for tok in ["fill", "title", "description", "field"]):
        textboxes = [e for e in scored_sorted if e.get("role") == "textbox" and e["id"] not in used_ids]
        for e in textboxes[:3]:
            selected.append(e)
            used_ids.add(e["id"])

    # ensure some comboboxes for select instructions
    if any(tok in instr_lc for tok in ["select", "dropdown", "choose", "option"]):
        combos = [e for e in scored_sorted if e.get("role") == "combobox" and e["id"] not in used_ids]
        for e in combos[:2]:
            selected.append(e)
            used_ids.add(e["id"])

    return selected, scored_sorted


def persist_scored(out_path: Path, base_meta: Dict, scored_all: List[Dict], top_k: List[Dict]) -> None:
    payload = dict(base_meta)
    payload["scored"] = scored_all
    payload["top_k"] = top_k
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
