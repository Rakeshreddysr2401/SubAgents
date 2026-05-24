"""Conversation agent — handles general queries, web search, vision, and system tasks."""

from langchain_core.messages import SystemMessage

from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.llm_config import llm
from src.tools.handover_tool import handover
from src.utils.message_utils import prepare_messages_for_agent, safe_invoke

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an intelligent AI assistant with access to webcam vision, system tools, and web search.

Capabilities:
- Answer general knowledge questions and help with research (use web search when needed)
- See what's in front of the webcam and describe it (use capture_webcam)
- Report system info like time and battery (use get_system_info)
- Open applications on the system (use open_mac_app)
- Engage in helpful conversation and small talk

Guidelines:
- Be direct and concise. Don't narrate tool usage — just use the tool and describe results.
- Use capture_webcam for visual questions; remember images from prior turns unless a fresh look is requested.
- For food orders, cart management, or Swiggy-specific tasks, call handover("supervisor", reason="food-related request").
- When done with your response and no further action is needed, just reply. Do not call handover unless routing is required.
"""


def conversation_node(state: AgentState):
    from src.tools import CONVERSATION_TOOLS
    llm_with_tools = llm.bind_tools(CONVERSATION_TOOLS)
    clean_messages = prepare_messages_for_agent(state["messages"])
    response = safe_invoke(llm_with_tools, [SystemMessage(content=_SYSTEM_PROMPT)] + clean_messages, logger)
    return {"messages": [response], "active_agent": "conversation"}
