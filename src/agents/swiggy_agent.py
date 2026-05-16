from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from src.states.states import AgentState
from src.llm_config import llm
from src.tools.swiggy_real_tools import REAL_SWIGGY_TOOLS
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

SWIGGY_SYSTEM_PROMPT = """\
You are a specialized Swiggy Food Ordering Sub-Agent using official Swiggy MCP tools.
Your goal is to help the user find restaurants, browse menus, and manage their food cart.

Available Tools:
1. swiggy_get_addresses: Use this to see where the user can order to.
2. swiggy_search_restaurants: Search for restaurants by name or cuisine.
3. swiggy_get_menu: Get the menu for a specific restaurant ID.
4. swiggy_update_cart: Add/remove items from the cart.
5. swiggy_track_order: Track an existing order.

Workflow:
- First, check addresses or search for restaurants based on user craving.
- Once a restaurant is found, get its menu.
- Help the user pick items and update the cart.
- Be helpful and descriptive with menu items and prices.\
"""

llm_with_swiggy_tools = llm.bind_tools(REAL_SWIGGY_TOOLS)

def swiggy_node(state: AgentState):
    messages = [SystemMessage(content=SWIGGY_SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_swiggy_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return END
    return "tools"

builder = StateGraph(AgentState)
builder.add_node("swiggy_node", swiggy_node)
builder.add_node("tools", ToolNode(REAL_SWIGGY_TOOLS))

builder.set_entry_point("swiggy_node")
builder.add_conditional_edges("swiggy_node", should_continue, ["tools", END])
builder.add_edge("tools", "swiggy_node")

swiggy_graph = builder.compile()
