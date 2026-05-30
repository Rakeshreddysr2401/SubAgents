from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode

from src.commons.constants import SUPERVISOR, CONVERSATION, SWIGGY, TRACKER
from src.states.states import AgentState
from src.tools import SUPERVISOR_TOOLS, CONVERSATION_TOOLS, SWIGGY_TOOLS, TRACKER_TOOLS
from src.agents.supervisor_agent import supervisor_node
from src.agents.conversation_agent import conversation_node
from src.agents.swiggy_agent import swiggy_node
from src.agents.tracker_agent import tracker_node
from src.nodes.turn_entry import turn_entry_node
from src.nodes.handle_handover import handle_handover, parse_handover
from src.tools.handover_tool import HANDOVER_NAMES
from src.configs.memory_config import get_memory


def _route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def _route_after_tools(state: AgentState, agent_name: str) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.name in HANDOVER_NAMES:
            return "handle_handover"
        if isinstance(msg, AIMessage):
            break
    return agent_name


def create_graph(checkpointer=None):
    builder = StateGraph(AgentState)

    # Utility nodes
    builder.add_node("turn_entry", turn_entry_node)
    builder.add_node("handle_handover", handle_handover)

    # Agent nodes
    builder.add_node(SUPERVISOR, supervisor_node)
    builder.add_node(CONVERSATION, conversation_node)
    builder.add_node(SWIGGY, swiggy_node)
    builder.add_node(TRACKER, tracker_node)

    # Per-agent tool nodes
    builder.add_node(f"{SUPERVISOR}_tools", ToolNode(tools=SUPERVISOR_TOOLS))
    builder.add_node(f"{CONVERSATION}_tools", ToolNode(tools=CONVERSATION_TOOLS))
    builder.add_node(f"{SWIGGY}_tools", ToolNode(tools=SWIGGY_TOOLS))
    builder.add_node(f"{TRACKER}_tools", ToolNode(tools=TRACKER_TOOLS))

    # Entry: every turn starts at turn_entry (resets loop guard, handles sticky routing)
    builder.add_edge(START, "turn_entry")
    # turn_entry routes via Command — no static edge needed

    # Agent → tools or END
    builder.add_conditional_edges(SUPERVISOR,    _route_after_agent, {"tools": f"{SUPERVISOR}_tools",    END: END})
    builder.add_conditional_edges(CONVERSATION,  _route_after_agent, {"tools": f"{CONVERSATION}_tools",  END: END})
    builder.add_conditional_edges(SWIGGY,        _route_after_agent, {"tools": f"{SWIGGY}_tools",        END: END})
    builder.add_conditional_edges(TRACKER,       _route_after_agent, {"tools": f"{TRACKER}_tools",       END: END})

    # Tools → handle_handover or back to same agent
    _agents = [SUPERVISOR, CONVERSATION, SWIGGY, TRACKER]
    for agent in _agents:
        builder.add_conditional_edges(
            f"{agent}_tools",
            lambda s, a=agent: _route_after_tools(s, a),
            {"handle_handover": "handle_handover", agent: agent},
        )

    # handle_handover → END (sticky) or Command(goto=agent) (chain) — no static edge needed
    builder.add_edge("handle_handover", END)

    return builder.compile(checkpointer=checkpointer)


graph = create_graph(checkpointer=get_memory())
__all__ = ["graph"]
