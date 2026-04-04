"""
Supervisor Agent — entry point for LangGraph Studio (langgraph dev).

Currently a minimal single-node chatbot.
Replace with full supervisor routing logic when sub-agents are ready.
"""

from langgraph.graph import StateGraph, END

from src.states.states import AgentState
from src.llm_config import llm
from src.configs.memory_config import get_memory


def chatbot_node(state: AgentState):
    """Simple LLM call — placeholder for the real supervisor router."""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


# Build graph
builder = StateGraph(AgentState)
builder.add_node("chatbot", chatbot_node)
builder.set_entry_point("chatbot")
builder.add_edge("chatbot", END)

graph = builder.compile(checkpointer=get_memory())
