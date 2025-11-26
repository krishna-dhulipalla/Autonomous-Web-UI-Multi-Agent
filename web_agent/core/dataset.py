import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict

from .types import AgentAState

DATASET_ROOT = Path("dataset")


def sanitize_filename(name: str) -> str:
    # Keep only alphanumerics, spaces, dashes, underscores
    s = re.sub(r"[^a-zA-Z0-9 \-_]", "", name)
    s = s.strip().replace(" ", "_")
    return s[:64]  # limit length


def init_dataset(user_query: str) -> str:
    DATASET_ROOT.mkdir(exist_ok=True)

    task_name = sanitize_filename(user_query)
    task_dir = DATASET_ROOT / task_name
    
    # If it exists, we might want to clear it or just use it. 
    # For now, we'll just ensure it exists.
    task_dir.mkdir(parents=True, exist_ok=True)

    # meta.json
    meta = {
        "task_name": task_name,
        "user_goal": user_query,
        "app_name": "web_agent",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    (task_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    steps_dir = task_dir / "steps"
    steps_dir.mkdir(exist_ok=True)

    print(f"[Dataset] Initialized dataset at {task_dir}")
    return str(task_dir)


def log_step(state: AgentAState) -> None:
    dataset_path = state.get("dataset_path")
    if not dataset_path:
        return

    task_dir = Path(dataset_path)
    step_num = state.get("step", 0)

    # We want step_01, step_02...
    step_name = f"step_{step_num:02d}"
    step_dir = task_dir / "steps" / step_name
    step_dir.mkdir(exist_ok=True)

    # 1. Raw Screenshot (Initial state)
    raw_path = state.get("screenshot_path")
    if raw_path and Path(raw_path).exists():
        try:
            shutil.copy2(raw_path, step_dir / "raw.png")
        except Exception as e:
            print(f"[Dataset] Failed to copy raw screenshot: {e}")

    # 2. After Action Screenshot
    after_path = state.get("after_screenshot")
    if after_path and Path(after_path).exists():
        try:
            shutil.copy2(after_path, step_dir / "after_action.png")
        except Exception as e:
            print(f"[Dataset] Failed to copy after_action screenshot: {e}")

    # 3. Elements JSON
    elements = state.get("elements") or []
    try:
        (step_dir / "elements.json").write_text(json.dumps(elements, indent=2))
    except Exception as e:
        print(f"[Dataset] Failed to write elements.json: {e}")

    # 4. Note (Explanation)
    instruction = state.get("instruction") or ""
    actions = state.get("actions") or []

    # Summarize actions
    action_desc = []
    for a in actions:
        act = a.get("action")
        tid = a.get("target_id")
        params = a.get("params")
        action_desc.append(f"{act} on {tid} ({params})")

    note_content = f"Instruction: {instruction}\nActions: {', '.join(action_desc)}\n"

    try:
        (step_dir / "note.txt").write_text(note_content)
    except Exception as e:
        print(f"[Dataset] Failed to write note.txt: {e}")
