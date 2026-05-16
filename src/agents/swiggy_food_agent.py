from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools.swiggy_mcp import get_swiggy_food_tools
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

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
"""


async def swiggy_food_node(state: AgentState):
    """LLM call with real Swiggy tools — initialises MCP session on first invocation."""
    tools = await get_swiggy_food_tools()
    llm_with_tools = llm.bind_tools(tools)
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}


async def swiggy_tools_node(state: AgentState):
    """Execute whichever Swiggy MCP tool the LLM called."""
    tools = await get_swiggy_food_tools()
    return await ToolNode(tools).ainvoke(state)


builder = StateGraph(AgentState)
builder.add_node("swiggy_food_node", swiggy_food_node)
builder.add_node("tools", swiggy_tools_node)

builder.set_entry_point("swiggy_food_node")
builder.add_conditional_edges("swiggy_food_node", tools_condition)
builder.add_edge("tools", "swiggy_food_node")

graph = builder.compile()
