"""
Supervisor Agent — entry point for LangGraph Studio (langgraph dev).
ReAct-style chatbot with tool calling (vision + memory).
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
You are a perceptual AI assistant with a live camera watching the user's environment.
You continuously absorb the environment through motion-triggered observations stored in a text log.

You have two tools:

1. recall_recent — reads the text log of what the camera observed in the last 5 minutes.
   Each log entry was captured by a vision model and includes: people, clothing colors, \
objects, actions, and the setting.
   Use for: past events, activity history, "what happened", "was there X", "what did you see".
   FAST — no camera call.

2. look_now — takes a fresh camera frame right now and asks the vision model your specific question.
   Use for: current real-time state, specific colors, counts, fine detail, "what am I doing now".
   SLOWER — calls the vision model.

Routing strategy:
- Always try recall_recent first.
- If the text log contains enough detail to answer accurately → answer directly from it.
- Only call look_now when the text log is missing the specific detail the user needs.
- If the user asks about "right now" or "currently" and freshness matters → use look_now.
- Never call both tools for the same question unless the first one is genuinely insufficient.

Answer clearly and directly. Cite time ("30 seconds ago", "2 minutes ago") when relevant.\
"""

llm_with_tools = llm.bind_tools(ALL_TOOLS)


def supervisor_node(state: AgentState):
    """LLM call — may produce tool_calls or a final response."""
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

# No checkpointer here — LangGraph Studio provides its own.
# For standalone mode (main.py), graph.py wraps this with a checkpointer.
graph = builder.compile()
