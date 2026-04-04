"""
Supervisor Agent — entry point for LangGraph Studio (langgraph dev).

Currently a minimal single-node chatbot.
Replace with full supervisor routing logic when sub-agents are ready.
"""

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from src.states.states import AgentState
from src.llm_config import llm
from src.configs.memory_config import get_memory
from src.configs.logging_config import get_logger

logger = get_logger(__name__)


def _build_vision_messages(messages, video_frames):
    """Replace the last user message with a multimodal message that includes video frames."""
    # Find the last HumanMessage and get its text
    last_human_idx = None
    last_human_text = ""
    for i in reversed(range(len(messages))):
        msg = messages[i]
        if isinstance(msg, HumanMessage) or (isinstance(msg, dict) and msg.get("role") == "user"):
            last_human_idx = i
            last_human_text = msg.content if hasattr(msg, "content") else msg.get("content", "")
            break

    if last_human_idx is None:
        return messages

    # Build multimodal content blocks
    content = [{"type": "text", "text": last_human_text}]
    for frame_b64 in video_frames:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"},
        })

    # Replace the last user message with the multimodal version
    updated = list(messages)
    updated[last_human_idx] = HumanMessage(content=content)
    return updated


def chatbot_node(state: AgentState):
    """LLM call with optional vision support for video frames."""
    messages = state["messages"]
    video_frames = state.get("video_frames") or []

    if video_frames:
        logger.info("Vision mode: including %d frame(s) in LLM call", len(video_frames))
        messages = _build_vision_messages(messages, video_frames)

    response = llm.invoke(messages)
    return {"messages": [response]}


# Build graph
builder = StateGraph(AgentState)
builder.add_node("chatbot", chatbot_node)
builder.set_entry_point("chatbot")
builder.add_edge("chatbot", END)

graph = builder.compile(checkpointer=get_memory())
