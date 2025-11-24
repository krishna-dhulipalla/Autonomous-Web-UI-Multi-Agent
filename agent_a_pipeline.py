"""
Entry point for Agent A: opens Linear, collects clickable elements,
takes a raw screenshot, and asks a vision LLM to suggest the next UI action.

The implementation is split into modular components under agent_a/.
"""

from __future__ import annotations
from agent_a.main import print_summary, run

USER_QUERY = "Create a new issue with title 'testing_issue 1', description 'created by multi-agent with playwright', set priority 'high', set assignee 'kdhulipalla13@gmail.com', set label as 'improvement' and set due date next week and then save it."


def main():
    final_state = run(USER_QUERY)
    print_summary(USER_QUERY, final_state)


if __name__ == "__main__":
    main()
