"""
Supervisor Agent — entry point for LangGraph Studio (langgraph dev).
ReAct-style chatbot with tool calling (vision, future YOLO, etc.).
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools import ALL_TOOLS
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

# Bind tools so GPT-4o-mini knows what it can call
llm_with_tools = llm.bind_tools(ALL_TOOLS)


def chatbot_node(state: AgentState):
    """LLM call — may produce tool_calls or a final response."""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


# Build graph: chatbot ─┬─(tool_calls)──► tools ──► chatbot
#                        └─(no tools)───► END
builder = StateGraph(AgentState)
builder.add_node("chatbot", chatbot_node)
builder.add_node("tools", ToolNode(ALL_TOOLS))

builder.set_entry_point("chatbot")
builder.add_conditional_edges("chatbot", tools_condition)
builder.add_edge("tools", "chatbot")

# No checkpointer here — LangGraph Studio provides its own.
# For standalone mode (main.py), graph.py wraps this with a checkpointer.
graph = builder.compile()
