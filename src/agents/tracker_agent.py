"""Tracker agent — checks delivery status of active and past Swiggy orders."""

from langchain_core.messages import SystemMessage

from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.llm_config import llm
from src.utils.message_utils import prepare_messages_for_agent, safe_invoke

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are a Swiggy order tracking assistant. Your job is to check delivery status
and keep the user informed about their active or past orders.

Capabilities via tools:
- Get a list of recent orders (get_food_orders)
- Get details for a specific order (get_food_order_details)
- Track a live delivery in real time (track_food_order)

Guidelines:
- When chained right after an order is placed, immediately check the order status and report it.
- Be concise: report estimated delivery time, current status, and restaurant name.
- If asked about a specific order, fetch its details and report clearly.
- Once you've answered the tracking question, call handover("supervisor", reason="tracking_done")
  so the supervisor can handle the user's next request.
- For food ordering (not tracking), call handover("supervisor", reason="ordering_request").
"""


def tracker_node(state: AgentState):
    from src.tools import TRACKER_TOOLS
    llm_with_tools = llm.bind_tools(TRACKER_TOOLS)
    clean_messages = prepare_messages_for_agent(state["messages"])
    response = safe_invoke(llm_with_tools, [SystemMessage(content=_SYSTEM_PROMPT)] + clean_messages, logger)
    return {"messages": [response], "active_agent": "tracker"}
