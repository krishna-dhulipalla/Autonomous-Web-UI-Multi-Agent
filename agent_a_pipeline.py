"""
Entry point for Agent A: opens Linear, collects clickable elements,
annotates top candidates, and asks a vision LLM to choose an element id.

The implementation is split into modular components under agent_a/.
"""

from __future__ import annotations

from agent_a.config import DEFAULT_GOAL_HINT
from agent_a.main import print_summary, run


def main():
    goal = DEFAULT_GOAL_HINT or "create a new issue"
    final_state = run(goal)
    print_summary(goal, final_state)


if __name__ == "__main__":
    main()

