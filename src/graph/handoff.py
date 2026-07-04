"""Guarded handoff tools for the swarm.

Mirrors `langgraph_swarm.create_handoff_tool` but preserves two behaviors from
the previous custom handover system:

1. **Reason bridge** — the calling agent must pass a `reason`; the receiving
   agent gets a SystemMessage bridge explaining why it now owns the turn.
2. **Loop guard** — each handoff increments `agent_turn_visits[target]`
   (reset per user turn by the /chat input). Past `max_agent_visits` the
   handoff is *refused* via ToolMessage, forcing the current agent to answer
   directly instead of ping-ponging.
"""

from typing import Annotated, Any

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from langgraph_swarm.handoff import METADATA_KEY_HANDOFF_DESTINATION

from src.commons.constants import AGENT_DESCRIPTIONS
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings

logger = get_logger(__name__)


def create_guarded_handoff_tool(*, agent_name: str, description: str | None = None) -> BaseTool:
    name = f"transfer_to_{agent_name}"
    desc = AGENT_DESCRIPTIONS.get(agent_name, agent_name)
    if description is None:
        description = (
            f"Transfer the conversation to the '{agent_name}' agent, "
            f"which handles: {desc}. Call this BEFORE answering when the "
            f"user's request belongs to that agent."
        )

    @tool(name, description=description)
    def handoff_to_agent(
        reason: Annotated[str, "Why you are transferring and what the next agent must do"],
        state: Annotated[Any, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        visits = dict(state.get("agent_turn_visits") or {})
        visits[agent_name] = visits.get(agent_name, 0) + 1

        if visits[agent_name] > get_settings().max_agent_visits:
            logger.warning(
                "Loop guard: refusing handoff to %s (visited %d times this turn)",
                agent_name, visits[agent_name],
            )
            return Command(
                update={
                    "agent_turn_visits": visits,
                    "messages": [
                        ToolMessage(
                            content=(
                                "Handoff refused: a routing loop was detected. "
                                "Do NOT call any transfer tool again this turn. "
                                "Answer the user directly in plain language with "
                                "whatever information you have."
                            ),
                            name=name,
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        logger.info("Handoff: → %s (reason: %s)", agent_name, reason or "unspecified")
        tool_message = ToolMessage(
            content=f"Successfully transferred to {agent_name}",
            name=name,
            tool_call_id=tool_call_id,
        )
        bridge = SystemMessage(
            content=(
                f"You are now the {agent_name} agent, responsible for: {desc}. "
                f"You were handed the conversation because: \"{reason or 'user request'}\". "
                f"Continue from the user's latest request without re-asking for "
                f"information already provided."
            )
        )
        return Command(
            goto=agent_name,
            graph=Command.PARENT,
            update={
                "messages": [*state["messages"], tool_message, bridge],
                "active_agent": agent_name,
                "agent_turn_visits": visits,
            },
        )

    handoff_to_agent.metadata = {METADATA_KEY_HANDOFF_DESTINATION: agent_name}
    return handoff_to_agent
