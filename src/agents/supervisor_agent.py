"""
Supervisor Agent — Multimodal ReAct-style agent.
Dynamically decides when to capture webcam frames and remembers them in conversation history.
"""

from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools import ALL_TOOLS
from src.agents.swiggy_food_agent import swiggy_food_node, swiggy_tools_node
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
async def transfer_to_swiggy():
    """Transfer the conversation to the Swiggy food ordering assistant.
    Use this when the user wants to search for restaurants, browse menus, 
    manage their food cart, or place a food delivery order.
    """
    return "Transferring to Swiggy food assistant..."

SYSTEM_PROMPT = """\
You are an intelligent, proactive AI Desktop Assistant. You have "eyes" through the webcam and a "voice" through the speakers.

Operational Guidelines:
1. **Be Direct (No Narration)**: Never say "I am now using my camera" or "I am looking at a frame." Just look and describe what you see immediately.
2. **Proactive Identification**: If you see multiple people and the user asks "What am I wearing?", don't ask who they are. Instead, describe all people present.
3. **Conversational Memory**: You remember images from previous turns.
4. **Tool Strategy**: 
    - Use 'capture_webcam' for environment/visual questions.
    - Use 'speak_out_loud' when verbal confirmation is appropriate.
    - Use 'get_system_info' for time/battery.
    - Use 'transfer_to_swiggy' when the user wants to order food or browse restaurants.

You are helpful, witty, and concise. Don't be robotic.\
"""

# Include transfer tool in the supervisor's toolset
SUPERVISOR_TOOLS = ALL_TOOLS + [transfer_to_swiggy]
llm_with_tools = llm.bind_tools(SUPERVISOR_TOOLS)


async def supervisor_node(state: AgentState):
    """LLM call — may produce tool_calls or a final response."""
    logger.info("Entering supervisor_node (active_agent=%s)", state.get("active_agent"))
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    # Explicitly confirm we are in supervisor mode
    return {"messages": [response], "active_agent": "supervisor"}


async def check_active_agent(state: AgentState):
    """Initial router to check if we should skip supervisor and go to active agent."""
    active = state.get("active_agent", "supervisor")
    logger.info("check_active_agent: thread_id routing. active_agent=%s", active)
    if active == "swiggy":
        return "swiggy_food_node"
    return "supervisor_node"


async def route_supervisor(state: AgentState):
    """Route from supervisor based on tool calls."""
    route = tools_condition(state)
    if route == END:
        return END
    return "tools"


async def route_swiggy(state: AgentState):
    """Route from swiggy based on tool calls."""
    route = tools_condition(state)
    if route == END:
        return END
    return "swiggy_tools"


async def post_tool_router(state: AgentState):
    """Decide where to go after tools are executed."""
    last_message = state["messages"][-1]
    
    # Check if the tool executed was a handoff tool
    content = str(last_message.content).lower()
    
    if "transferring to swiggy" in content:
        return "activate_swiggy"
    if "transferring back to supervisor" in content:
        return "activate_supervisor"
    
    # Default: return to whichever agent is currently active in state
    active = state.get("active_agent", "supervisor")
    if active == "swiggy":
        return "swiggy_food_node"
    return "supervisor_node"


async def activate_swiggy(state: AgentState):
    """Transition node to set active_agent to swiggy."""
    logger.info("Activating Swiggy agent")
    return {"active_agent": "swiggy"}


async def activate_supervisor(state: AgentState):
    """Transition node to set active_agent to supervisor."""
    logger.info("Activating Supervisor agent")
    return {"active_agent": "supervisor"}


async def supervisor_tools_node(state: AgentState):
    """Execute whichever tool the LLM called (supervisor tools)."""
    logger.info("Executing supervisor_tools_node with %d tools", len(SUPERVISOR_TOOLS))
    return await ToolNode(SUPERVISOR_TOOLS).ainvoke(state)

# Build graph
builder = StateGraph(AgentState)
builder.add_node("supervisor_node", supervisor_node)
builder.add_node("tools", supervisor_tools_node)
builder.add_node("swiggy_food_node", swiggy_food_node)
builder.add_node("swiggy_tools", swiggy_tools_node)
builder.add_node("activate_swiggy", activate_swiggy)
builder.add_node("activate_supervisor", activate_supervisor)

# Entry point checks active agent
builder.set_conditional_entry_point(
    check_active_agent,
    {
        "swiggy_food_node": "swiggy_food_node",
        "supervisor_node": "supervisor_node"
    }
)

# Supervisor flow
builder.add_conditional_edges("supervisor_node", route_supervisor, {"tools": "tools", END: END})
builder.add_conditional_edges("tools", post_tool_router, {
    "activate_swiggy": "activate_swiggy",
    "activate_supervisor": "activate_supervisor",
    "supervisor_node": "supervisor_node"
})
builder.add_edge("activate_swiggy", "swiggy_food_node")
builder.add_edge("activate_supervisor", "supervisor_node")

# Swiggy flow
builder.add_conditional_edges("swiggy_food_node", route_swiggy, {"swiggy_tools": "swiggy_tools", END: END})
builder.add_conditional_edges("swiggy_tools", post_tool_router, {
    "activate_swiggy": "activate_swiggy",
    "activate_supervisor": "activate_supervisor",
    "swiggy_food_node": "swiggy_food_node"
})

graph = builder.compile()
