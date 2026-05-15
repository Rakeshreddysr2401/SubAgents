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
You are a multimodal AI Desktop Assistant running on a Mac. You have access to the webcam, speakers, and system controls.

Capabilities & Rules:
1. **Vision**: If the user asks about their environment, appearance, or anything visual, use 'capture_webcam'. You remember previous images in the history.
2. **Speech**: Use 'speak_out_loud' to talk to the user verbally when appropriate or requested.
3. **System**: Use 'get_system_info' for time, date, or battery. Use 'open_mac_app' to help the user launch applications.
4. **Context**: Only use tools when the current conversation history is insufficient. Be proactive but concise.

You are friendly, efficient, and helpful.\
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
