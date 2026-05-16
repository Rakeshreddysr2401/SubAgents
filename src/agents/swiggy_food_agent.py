from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools.swiggy_mcp import get_swiggy_food_tools
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
async def transfer_to_supervisor():
    """Transfer the conversation back to the main supervisor assistant.
    Use this when you have finished helping the user with their food-related request,
    or if the user wants to talk about something unrelated to Swiggy/food.
    """
    return "Transferring back to supervisor..."

SYSTEM_PROMPT = """\
You are a Swiggy food ordering assistant. Help users discover restaurants, browse menus,
manage their cart, and place food delivery orders.

Capabilities you have via tools:
- Search restaurants and dishes by cuisine, location, or name
- Browse full restaurant menus with variants and add-ons
- Get saved delivery addresses
- Manage cart: view, add/modify items, flush, apply coupons
- Place orders and track live delivery

Guidelines:
- Always confirm delivery address before placing an order.
- Ask for clarification on item variants (size, spice level, add-ons) when relevant.
- Show a cart summary before placing an order and require explicit user confirmation.
- Be concise — show name, price, and rating rather than dumping full menus.
- If the user is undecided, suggest popular or highly rated items.
- Never place an order without the user saying "yes", "confirm", or equivalent.
- If the user wants to do something unrelated to food or says goodbye, use 'transfer_to_supervisor'.
"""


async def swiggy_food_node(state: AgentState):
    """LLM call with real Swiggy tools — initialises MCP session on first invocation."""
    logger.info("Entering swiggy_food_node")
    tools = await get_swiggy_food_tools()
    # Add transfer tool to Swiggy tools
    all_swiggy_tools = list(tools) + [transfer_to_supervisor]
    llm_with_tools = llm.bind_tools(all_swiggy_tools)

    # Prepend Swiggy system prompt
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)

    return {"messages": [response], "active_agent": "swiggy"}



async def swiggy_tools_node(state: AgentState):
    """Execute whichever Swiggy MCP tool the LLM called."""
    tools = await get_swiggy_food_tools()
    if not isinstance(tools, list):
        logger.error("get_swiggy_food_tools() did not return a list: %s", type(tools))
        raise TypeError(f"Expected list of tools, got {type(tools)}")
        
    all_swiggy_tools = list(tools) + [transfer_to_supervisor]
    logger.info("Executing swiggy_tools_node with %d tools", len(all_swiggy_tools))
    return await ToolNode(all_swiggy_tools).ainvoke(state)

# Compile graph for standalone usage (as referenced in langgraph.json)
builder = StateGraph(AgentState)
builder.add_node("swiggy_food_node", swiggy_food_node)
builder.add_node("tools", swiggy_tools_node)

builder.set_entry_point("swiggy_food_node")
builder.add_conditional_edges("swiggy_food_node", tools_condition, {"tools": "tools", END: END})
builder.add_edge("tools", "swiggy_food_node")

graph = builder.compile()
