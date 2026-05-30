"""Supervisor — pure router. Always calls handover(), never responds to the user directly."""

from langchain_core.messages import AIMessage, SystemMessage

from src.commons.constants import SUPERVISOR
from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.llm_config import llm
from src.tools.handover_tool import handover, HANDOVER_NAMES
from src.utils.message_utils import prepare_messages_for_agent, safe_invoke

logger = get_logger(__name__)

_llm_with_tools = llm.bind_tools([handover])


def _build_prompt(state: AgentState) -> str:
    return """\
You are a routing supervisor. Your ONLY job is to decide which agent should handle the user's request and call handover() immediately. You NEVER respond to the user with text.

Available agents:
- "conversation": general questions, web search, system info, visual/webcam queries, small talk, anything not food-related
- "swiggy": food ordering, restaurant search, browsing menus, managing cart, placing Swiggy orders
- "tracker": checking delivery status of an active or past Swiggy order

Rules:
1. Always call handover() — never write a text response.
2. Route to "swiggy" if the user wants to order food, search restaurants, manage cart, or anything involving placing a Swiggy order.
3. Route to "tracker" if the user asks about order status, delivery ETA, or tracking a Swiggy order.
4. Route to "conversation" for everything else.
5. Pass a short reason describing why (e.g. "user wants to order food", "user asking about delivery").
"""


def supervisor_node(state: AgentState):
    clean_messages = prepare_messages_for_agent(state["messages"], keep_all_system_msgs=True)
    response = safe_invoke(_llm_with_tools, [SystemMessage(content=_build_prompt(state))] + clean_messages, logger)
    # Strip any text alongside the handover call — supervisor must stay silent
    if response.tool_calls and any(tc["name"] in HANDOVER_NAMES for tc in response.tool_calls):
        response = AIMessage(content="", tool_calls=response.tool_calls, id=response.id)
    return {"messages": [response], "active_agent": SUPERVISOR}
