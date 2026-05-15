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
You are a perceptual AI assistant with a live camera and specialized sub-agents.
You continuously absorb the environment through motion-triggered observations stored in a text log.

You have three main capabilities:

1. recall_recent — reads the text log of what the camera observed in the last 5 minutes.
   FAST — no camera call.

2. look_now — takes a fresh camera frame right now and asks the vision model your specific question.
   SLOWER — calls the vision model.

3. call_swiggy_agent — delegates food ordering, restaurant searching, and checkout tasks.
   Use this for ANY request related to food, Swiggy, restaurants, or delivery.

Routing strategy:
- For general environmental questions, try recall_recent first.
- Only call look_now for real-time visual detail not in the log.
- For ANY food or restaurant related query, immediately use call_swiggy_agent.
- Answer clearly and directly. Cite time when relevant.\
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
