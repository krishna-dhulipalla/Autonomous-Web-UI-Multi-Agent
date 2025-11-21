from pathlib import Path
from typing import List

from .config import OUT_DIR
from .scoring import persist_scored, select_top
from .types import AgentAState


def score_elements(state: AgentAState) -> AgentAState:
    """Score elements using the instruction and select top 10."""
    instruction = state.get("instruction") or ""
    elements = state.get("elements") or []
    tried_ids: List[str] = state.get("tried_ids") or []

    if not instruction:
        raise RuntimeError("No instruction available for scoring.")

    top_k, scored_all = select_top(elements, instruction, top_k=10, tried_ids=tried_ids)

    # Persist scored results alongside the existing metadata
    meta_path = OUT_DIR / "elements.json"
    base_meta = {}
    if meta_path.exists():
        try:
            import json

            base_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            base_meta = {}

    base_meta.setdefault("user_query", state.get("user_query"))
    base_meta.setdefault("screenshot", state.get("screenshot_path"))

    persist_scored(meta_path, base_meta, scored_all, top_k)

    state["top_elements"] = top_k
    return state

