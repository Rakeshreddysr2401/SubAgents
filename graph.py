from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from src.states.states import AgentState
from src.tools import SUPERVISOR_TOOLS, CONVERSATION_TOOLS, SWIGGY_TOOLS, TRACKER_TOOLS
from src.agents.supervisor_agent import supervisor_node
from src.agents.conversation_agent import conversation_node
from src.agents.swiggy_agent import swiggy_node
from src.agents.tracker_agent import tracker_node
from src.agents.handover import apply_handover, respond_then_wait, respond_and_chain, parse_handover
from src.tools.handover_tool import HANDOVER_NAMES
from src.configs.memory_config import get_memory

_HANDOVER_ROUTES = {
    "apply_handover": "apply_handover",
    "respond_then_wait": "respond_then_wait",
    "respond_and_chain": "respond_and_chain",
}


def _route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def _route_after_tools(state: AgentState, agent_name: str) -> str:
    has_handover = False
    chain = False
    ai_content = ""

    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            if msg.name in HANDOVER_NAMES:
                has_handover = True
                _, _, chain = parse_handover(msg.content)
        elif isinstance(msg, AIMessage):
            ai_content = msg.content
            break

    if not has_handover:
        return agent_name
    if not ai_content:
        return "apply_handover"
    return "respond_and_chain" if chain else "respond_then_wait"


def create_graph(checkpointer=None):
    builder = StateGraph(AgentState)

    # Agent nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("conversation", conversation_node)
    builder.add_node("swiggy", swiggy_node)
    builder.add_node("tracker", tracker_node)

    # Per-agent tool nodes
    builder.add_node("supervisor_tools", ToolNode(tools=SUPERVISOR_TOOLS))
    builder.add_node("conversation_tools", ToolNode(tools=CONVERSATION_TOOLS))
    builder.add_node("swiggy_tools", ToolNode(tools=SWIGGY_TOOLS))
    builder.add_node("tracker_tools", ToolNode(tools=TRACKER_TOOLS))

    # Handover handler nodes
    builder.add_node("apply_handover", apply_handover)
    builder.add_node("respond_then_wait", respond_then_wait)
    builder.add_node("respond_and_chain", respond_and_chain)

    # Entry: always start at supervisor
    builder.add_edge(START, "supervisor")

    # Agent → tools or END
    builder.add_conditional_edges("supervisor",    _route_after_agent, {"tools": "supervisor_tools",    END: END})
    builder.add_conditional_edges("conversation",  _route_after_agent, {"tools": "conversation_tools",  END: END})
    builder.add_conditional_edges("swiggy",        _route_after_agent, {"tools": "swiggy_tools",        END: END})
    builder.add_conditional_edges("tracker",       _route_after_agent, {"tools": "tracker_tools",       END: END})

    # Tools → handover routing or back to agent
    builder.add_conditional_edges("supervisor_tools",   lambda s: _route_after_tools(s, "supervisor"),   {**_HANDOVER_ROUTES, "supervisor":   "supervisor"})
    builder.add_conditional_edges("conversation_tools", lambda s: _route_after_tools(s, "conversation"), {**_HANDOVER_ROUTES, "conversation": "conversation"})
    builder.add_conditional_edges("swiggy_tools",       lambda s: _route_after_tools(s, "swiggy"),       {**_HANDOVER_ROUTES, "swiggy":       "swiggy"})
    builder.add_conditional_edges("tracker_tools",      lambda s: _route_after_tools(s, "tracker"),      {**_HANDOVER_ROUTES, "tracker":      "tracker"})

    # Handover exits: apply_handover and respond_and_chain route via Command (no edges needed)
    builder.add_edge("respond_then_wait", END)

    return builder.compile(checkpointer=checkpointer)


graph = create_graph(checkpointer=get_memory())
__all__ = ["graph"]
