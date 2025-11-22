"""
Entry point for Agent A: opens Linear, collects clickable elements,
takes a raw screenshot, and asks a vision LLM to suggest the next UI action.

The implementation is split into modular components under agent_a/.
"""

from __future__ import annotations
from agent_a.main import print_summary, run

USER_QUERY = "create a new project with title testing, which has priority high with target set to next week and keep remain same everything"


def main():
    final_state = run(USER_QUERY)
    print_summary(USER_QUERY, final_state)


if __name__ == "__main__":
    main()
