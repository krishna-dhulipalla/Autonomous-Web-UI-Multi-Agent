import re
import json
from typing import Dict, List, Optional, Set

# --- Configuration & Constants ---

# Base role weights (reduced importance)
BASE_ROLE_WEIGHTS = {
    "button": 1.0,
    "link": 1.0,
    "combobox": 1.0,
    "textbox": 1.0,
    "textarea": 1.0,
    "searchbox": 1.0,
    "option": 0.8,
    "menuitem": 0.8,
    "checkbox": 0.8,
    "radio": 0.8,
    "tab": 0.8,
}

# Intent Categories & Keywords
INTENT_KEYWORDS = {
    "profile_settings": {"profile", "account", "settings", "preferences", "full name", "display name", "avatar", "picture", "password", "email"},
    "create_new": {"create", "new", "add", "start", "open new"},
    "filter_search": {"filter", "search", "find", "narrow", "show only", "query"},
    "navigate_tab": {"go to", "switch to", "tab", "view", "section", "page"},
    "form_fill": {"fill", "enter", "type", "set", "update", "form", "field", "submit", "save"},
}

# Negative Signals (Domain Conflicts)
# If intent is X, penalize elements with Y tokens
NEGATIVE_SIGNALS = {
    "profile_settings": {"issue", "ticket", "task", "filter", "inbox", "project", "create"},
    "create_new": {"filter", "search", "settings", "profile", "logout"},
    "filter_search": {"create", "new", "settings", "profile", "logout"},
}

# Generic Chrome Tokens (always slight penalty if no specific match)
GENERIC_TOKENS = {"workspace", "help", "menu", "sidebar", "navigation"}

DESTRUCTIVE_TOKENS = {"delete", "remove",
                      "discard", "close", "dismiss", "trash"}


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-zA-Z0-9]+", text.lower()) if t]


def _classify_intent(instruction: str) -> str:
    """Classify instruction into a high-level intent."""
    instr_lower = instruction.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw in instr_lower:
                return intent
    return "generic"


def _score_lexical_match(instruction: str, name: str, instr_tokens: List[str], name_tokens: List[str]) -> float:
    """Layer 1: Lexical Match (Primary Driver)."""
    score = 0.0

    # Exact phrase match (high bonus)
    if name and name.lower() in instruction.lower():
        # Boost more if the name is significant length
        if len(name) > 3:
            score += 5.0
        else:
            score += 2.0

    # Token overlap
    if not instr_tokens or not name_tokens:
        return score

    instr_set = set(instr_tokens)
    name_set = set(name_tokens)
    intersection = instr_set & name_set

    # Jaccard-ish score but weighted by intersection size
    overlap_count = len(intersection)
    if overlap_count > 0:
        score += 3.0 * overlap_count

    return score


def _score_role_bias(role: str, landmark: str, intent: str, name_tokens: Set[str]) -> float:
    """Layer 2: Intent-Aware Role Bias."""
    score = BASE_ROLE_WEIGHTS.get(role, 0.5)

    # Intent-specific boosts
    if intent == "profile_settings":
        if any(t in name_tokens for t in {"settings", "profile", "account", "workspace"}):
            score += 2.0
        if landmark in {"navigation", "banner", "contentinfo"}:
            score += 1.0

    elif intent == "create_new":
        if any(t in name_tokens for t in {"create", "new", "add"}):
            score += 2.0
        if landmark == "main":
            score += 1.0

    elif intent == "filter_search":
        if any(t in name_tokens for t in {"filter", "search"}):
            score += 2.0

    elif intent == "form_fill":
        if role in {"textbox", "textarea", "combobox", "checkbox", "radio"}:
            score += 1.5
        if landmark == "main":
            score += 1.0

    return score


def _score_negative_signals(intent: str, name_tokens: Set[str], instr_tokens: Set[str]) -> float:
    """Layer 3: Negative Signals."""
    penalty = 0.0

    # Domain conflict
    conflict_tokens = NEGATIVE_SIGNALS.get(intent, set())
    if conflict_tokens & name_tokens:
        # Only penalize if the instruction DOESN'T explicitly ask for it
        # (e.g. "Filter by issue status" -> issue is fine)
        if not (conflict_tokens & instr_tokens):
            penalty -= 2.0

    # Generic chrome penalty
    if name_tokens & GENERIC_TOKENS:
        penalty -= 0.5

    # Destructive penalty
    if any(tok in DESTRUCTIVE_TOKENS for tok in name_tokens):
        if not any(tok in DESTRUCTIVE_TOKENS for tok in instr_tokens):
            penalty -= 3.0

    return penalty


def is_garbage_name(name: str) -> bool:
    """Return True if name is likely garbage."""
    if not name:
        return False
    if name.isdigit():
        return True
    if len(name) < 3 and name.lower() not in {"ok", "go", "id", "up", "to", "at", "in", "on", "by"}:
        return True
    return False


def score_element(elem: Dict, instruction: str, tried_ids: Optional[List[str]] = None, ui_same: bool = False) -> float:
    """
    Score an element based on 4-layer logic:
    1. Lexical Match (Primary)
    2. Intent-Aware Role Bias
    3. Negative Signals
    4. Heuristics (Retry, Garbage)
    """
    name = (elem.get("name") or "").strip()
    role = elem.get("role") or ""
    landmark = elem.get("landmark") or ""
    placeholder = (elem.get("placeholder") or "").strip()
    elem_id = elem.get("id") or ""

    # Combined name for matching
    full_name = (name + " " + placeholder).strip()

    instr_tokens = tokenize(instruction)
    name_tokens = tokenize(full_name)
    instr_set = set(instr_tokens)
    name_set = set(name_tokens)

    intent = _classify_intent(instruction)

    score = 0.0

    # Layer 1: Lexical Match
    score += _score_lexical_match(instruction,
                                  full_name, instr_tokens, name_tokens)

    # Layer 2: Intent-Aware Role Bias
    score += _score_role_bias(role, landmark, intent, name_set)

    # Layer 3: Negative Signals
    score += _score_negative_signals(intent, name_set, instr_set)

    # Layer 4: Heuristics

    # Retry penalty
    if tried_ids and elem_id in tried_ids:
        if ui_same:
            score -= 5.0
        else:
            score -= 1.5

    # Garbage name penalty
    if is_garbage_name(name):
        score -= 5.0

    return score


def persist_scored(out_path, base_meta: Dict, scored_all: List[Dict], top_k: List[Dict]) -> None:
    payload = dict(base_meta)
    payload["scored"] = scored_all
    payload["top_k"] = top_k
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        print(f"[Scoring] Failed to persist scored elements: {e}")
