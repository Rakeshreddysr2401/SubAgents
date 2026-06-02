"""Tracker agent — checks delivery status of active and past Swiggy orders."""

from langchain_core.messages import SystemMessage

from src.commons.constants import TRACKER
from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.llm_config import llm
from src.utils.message_utils import prepare_messages_for_agent, safe_invoke
from src.prompts.tracker import build_prompt

logger = get_logger(__name__)


def tracker_node(state: AgentState):
    from src.tools import TRACKER_TOOLS
    llm_with_tools = llm.bind_tools(TRACKER_TOOLS)
    clean_messages = prepare_messages_for_agent(state["messages"])
    response = safe_invoke(llm_with_tools, [SystemMessage(content=build_prompt(state))] + clean_messages, logger)
    return {"messages": [response], "active_agent": TRACKER}
