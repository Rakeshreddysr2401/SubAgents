"""
Supervisor Agent — Multimodal ReAct-style agent.
Dynamically decides when to capture webcam frames and remembers them in conversation history.
"""

from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools import ALL_TOOLS
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """\
You are an intelligent, proactive AI Desktop Assistant. You have "eyes" through the webcam and a "voice" through the speakers.

Operational Guidelines:
1. **Be Direct (No Narration)**: Never say "I am now using my camera" or "I am looking at a frame." Just look and describe what you see immediately.
2. **Proactive Identification**: If you see multiple people and the user asks "What am I wearing?", don't ask who they are. Instead, describe all people present (e.g., "The person on the left is in blue, and the person on the right is in red").
3. **Conversational Memory**: You remember images from previous turns. If the user asks a follow-up about something you already saw, don't capture a new image unless they specifically ask for a "fresh look" or if the scene has likely changed.
4. **Tool Strategy**: 
    - Use 'capture_webcam' for environment/visual questions.
    - Use 'speak_out_loud' when verbal confirmation is appropriate.
    - Use 'get_system_info' for time/battery.
    - Use 'call_swiggy_agent' for ANY food-related request (ordering, searching restaurants, tracking delivery).

You are helpful, witty, and concise. Don't be robotic.\
"""

llm_with_tools = llm.bind_tools(ALL_TOOLS)


def supervisor_node(state: AgentState):
    """LLM call — may produce tool_calls or a final response."""
    # Ensure all state fields exist to prevent errors
    state.setdefault("active_agent", "supervisor")
    state.setdefault("user_context", {})
    
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# Build graph: supervisor ─┬─(tool_calls)──► tools ──► supervisor
#                           └─(no tools)───► END
builder = StateGraph(AgentState)
builder.add_node("supervisor_node", supervisor_node)
builder.add_node("tools", ToolNode(ALL_TOOLS))

builder.set_entry_point("supervisor_node")
builder.add_conditional_edges("supervisor_node", tools_condition)
builder.add_edge("tools", "supervisor_node")

graph = builder.compile()
