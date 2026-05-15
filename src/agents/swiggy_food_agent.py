from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools.swiggy_mcp import SWIGGY_FOOD_TOOLS
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

if not SWIGGY_FOOD_TOOLS:
    logger.warning(
        "Swiggy Food Agent: no MCP tools loaded. "
        "Set SWIGGY_ACCESS_TOKEN in .env and ensure mcp.swiggy.com is reachable."
    )

SYSTEM_PROMPT = """\
You are a Swiggy food ordering assistant. Help users discover restaurants, browse menus,
manage their cart, and place food delivery orders.

Capabilities you have via tools:
- Search restaurants and dishes by cuisine, location, or name (search_restaurants, search_menu)
- Browse full restaurant menus with variants and add-ons (get_restaurant_menu)
- Get saved delivery addresses (get_addresses)
- Manage cart: view, add/modify items, flush, apply coupons (get_food_cart, update_food_cart, flush_food_cart, fetch_food_coupons, apply_food_coupon)
- Place orders (place_food_order)
- Track live delivery and check past orders (get_food_orders, get_food_order_details, track_food_order)

Guidelines:
- Always confirm delivery address before placing an order.
- Ask for clarification on item variants (size, spice level, add-ons) when relevant.
- Show a cart summary before placing an order and require explicit user confirmation.
- Be concise — show name, price, and rating rather than dumping full menus.
- If the user is undecided, suggest popular or highly rated items.
- Never place an order without the user saying "yes", "confirm", or equivalent.
"""

llm_with_tools = llm.bind_tools(SWIGGY_FOOD_TOOLS)


def swiggy_food_node(state: AgentState):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


builder = StateGraph(AgentState)
builder.add_node("swiggy_food_node", swiggy_food_node)
builder.add_node("tools", ToolNode(SWIGGY_FOOD_TOOLS))

builder.set_entry_point("swiggy_food_node")
builder.add_conditional_edges("swiggy_food_node", tools_condition)
builder.add_edge("tools", "swiggy_food_node")

graph = builder.compile()
