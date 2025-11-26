"""
Entry point for Agent A: opens Linear, collects clickable elements,
takes a raw screenshot, and asks a vision LLM to suggest the next UI action.

The implementation is split into modular components under agent_a/.
"""

from __future__ import annotations
from web_agent.core.orchestrator import print_summary, run

USER_QUERY = "Find the issue 'UI glitch on dashboard' if not found create one, change its priority to Urgent, add the label 'frontend', and mark staus as 'In Progress'."


def main():
    final_state = run(USER_QUERY)
    print_summary(USER_QUERY, final_state)


if __name__ == "__main__":
    main()
