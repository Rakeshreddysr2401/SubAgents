"""Swiggy agent — handles food ordering, restaurant search, cart, and order placement."""

from langchain_core.messages import SystemMessage

from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.llm_config import llm
from src.utils.message_utils import prepare_messages_for_agent, safe_invoke

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a Swiggy food ordering assistant. Help users discover restaurants, browse menus,
manage their cart, and place food delivery orders.

Capabilities via tools:
- Search restaurants and dishes by cuisine, location, or name
- Browse restaurant menus with variants and add-ons
- Get saved delivery addresses
- Manage cart: view, add/modify items, apply coupons, flush
- Place orders

Guidelines:
- Always confirm delivery address before placing an order.
- Ask for clarification on item variants (size, spice level, add-ons) when relevant.
- Show a cart summary before placing an order and require explicit user confirmation.
- Never place an order without the user saying "yes", "confirm", or equivalent.
- After successfully placing an order, respond with a confirmation message and call:
    handover("tracker", reason="order_placed", chain=True)
  so the tracker agent can immediately follow the delivery.
- For non-food questions, call handover("supervisor", reason="not food related").
"""


def swiggy_node(state: AgentState):
    from src.tools import SWIGGY_TOOLS
    llm_with_tools = llm.bind_tools(SWIGGY_TOOLS)
    clean_messages = prepare_messages_for_agent(state["messages"])
    response = safe_invoke(llm_with_tools, [SystemMessage(content=_SYSTEM_PROMPT)] + clean_messages, logger)
    return {"messages": [response], "active_agent": "swiggy"}
