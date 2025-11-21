from pathlib import Path
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .imaging import image_to_data_url
from .types import AgentAOutput, AgentAState


def _format_candidates(elements: List[dict]) -> str:
    lines = []
    for e in elements:
        label = e.get("name") or "(no name)"
        lines.append(f"- {e['id']}: {label}")
    return "\n".join(lines)


def agent_a(state: AgentAState) -> AgentAState:
    """Vision LLM node: choose id based on goal + candidates + annotated image."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.1)

    top_elements = state["top_elements"]
    if not top_elements:
        raise RuntimeError("No top elements available for Agent A.")

    elements_block = _format_candidates(top_elements)
    annotated_path = Path(state["annotated_path"])
    data_url = image_to_data_url(annotated_path)

    system_msg = SystemMessage(
        content=(
            "You are Agent A, a UI decision-maker. "
            "You see a screenshot with red boxes and numeric ids, "
            "and a list of candidate elements (id: name). "
            "Choose exactly ONE id that best matches the user's goal. "
            "Avoid dismiss/close/delete actions unless the goal explicitly asks for them. "
            "Respond strictly as JSON with keys 'chosen_id' and 'reason'."
        )
    )

    human_content = [
        {
            "type": "text",
            "text": (
                f"Goal:\n{state['goal']}\n\n"
                f"Candidate elements (id: name):\n{elements_block}\n\n"
                "Look at the screenshot to understand layout and context, "
                "but you must choose one of the ids listed above."
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": data_url},
        },
    ]
    human_msg = HumanMessage(content=human_content)

    structured_llm = llm.with_structured_output(AgentAOutput)
    result: AgentAOutput = structured_llm.invoke([system_msg, human_msg])

    state["chosen_id"] = result.chosen_id
    state["reason"] = result.reason
    return state

