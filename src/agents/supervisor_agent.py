"""Supervisor — pure router. Always calls handover(), never responds to the user directly."""

from langchain_core.messages import AIMessage, SystemMessage

from src.commons.constants import SUPERVISOR
from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.llm_config import llm
from src.tools.handover_tool import handover, HANDOVER_NAMES
from src.utils.message_utils import prepare_messages_for_agent, safe_invoke
from src.prompts.supervisor import build_prompt

logger = get_logger(__name__)

_llm_with_tools = llm.bind_tools([handover])


def supervisor_node(state: AgentState):
    from src.commons.constants import CONVERSATION
    clean_messages = prepare_messages_for_agent(state["messages"], keep_all_system_msgs=True)
    response = safe_invoke(_llm_with_tools, [SystemMessage(content=build_prompt(state))] + clean_messages, logger)

    has_handover = response.tool_calls and any(tc["name"] in HANDOVER_NAMES for tc in response.tool_calls)

    if not has_handover:
        # LLM skipped handover — force-route to conversation as a safe fallback
        logger.warning("Supervisor did not call handover(); forcing route to conversation")
        fallback_tc = {
            "name": "handover",
            "args": {"next_agent": CONVERSATION, "reason": "supervisor fallback"},
            "id": "supervisor_fallback",
            "type": "tool_call",
        }
        response = AIMessage(content="", tool_calls=[fallback_tc], id=response.id)
    else:
        # Strip any text alongside the handover call — supervisor must stay silent
        response = AIMessage(content="", tool_calls=response.tool_calls, id=response.id)

    return {"messages": [response], "active_agent": SUPERVISOR}
