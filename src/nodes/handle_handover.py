"""handle_handover — single centralized handover resolver.

Replaces the three separate apply_handover / respond_then_wait / respond_and_chain nodes.
Decision logic:
  - agent was silent (no AI text) OR chain=True  →  Command(goto=next_agent)  [immediate chain]
  - agent spoke AND chain=False                  →  dict(active_agent=next_agent) + END  [sticky]
"""

import json
import os
from typing import NamedTuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command
from src.commons.constants import CONVERSATION,SUPERVISOR,AGENT_DESCRIPTIONS
from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.tools.handover_tool import HANDOVER_NAMES

logger = get_logger(__name__)

_MAX_VISITS_PER_AGENT = int(os.getenv("MAX_AGENT_VISITS", "3"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_handover(content: str) -> tuple[str, str, bool]:
    try:
        data = json.loads(content)
        return data["next_agent"], data.get("reason", ""), bool(data.get("chain", False))
    except (json.JSONDecodeError, KeyError):
        # Fallback for legacy pipe-delimited format
        parts = content.split("|", 2)
        agent = parts[0].strip()
        reason = parts[1].strip() if len(parts) > 1 else ""
        chain = parts[2].strip().lower() == "true" if len(parts) > 2 else False
        return agent, reason, chain


def _extract_handover_context(state: AgentState) -> tuple[str, str, bool, str]:
    """Return (next_agent, reason, chain, ai_content) from the most recent handover."""
    next_agent = reason = ai_content = ""
    chain = False
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.name in HANDOVER_NAMES:
            next_agent, reason, chain = parse_handover(msg.content)
        elif isinstance(msg, AIMessage):
            ai_content = msg.content if isinstance(msg.content, str) else ""
            break
    return next_agent, reason, chain, ai_content


def _last_user_query(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else ""
    return ""


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

class HandoverResolution(NamedTuple):
    next_agent: str
    bridge_messages: list


def _resolve_handover(state: AgentState, raw_next_agent: str, reason: str) -> HandoverResolution:
    current = state.get("active_agent", SUPERVISOR)
    user_query = _last_user_query(state)
    next_agent = raw_next_agent

    if next_agent == SUPERVISOR:
        if reason == "cannot_answer":
            bridge_content = (
                f"The previous agent ('{current}') could not answer the user's question. "
                f"Do NOT route back to '{current}'. Try a different agent.\n"
                f"The user asked: \"{user_query}\""
            )
        else:
            bridge_content = "Route to the appropriate agent based on the conversation."
    else:
        desc = AGENT_DESCRIPTIONS.get(next_agent, next_agent)
        bridge_content = (
            f"You are the {next_agent} agent, responsible for: {desc}.\n"
            f"You were called because: \"{reason or 'user request'}\". "
            f"The user said: \"{user_query}\". "
            f"Handle this directly without re-asking what was already provided."
        )

    logger.info("Handover resolved: %s → %s (reason: %s)", current, next_agent, reason or "normal")
    return HandoverResolution(
        next_agent=next_agent,
        bridge_messages=[SystemMessage(content=bridge_content)],
    )


# ---------------------------------------------------------------------------
# Single handler node
# ---------------------------------------------------------------------------

def handle_handover(state: AgentState):
    next_agent, reason, chain, ai_content = _extract_handover_context(state)

    if not next_agent:
        logger.warning("handle_handover: no handover tool message found")
        return Command(goto=SUPERVISOR, update={})

    res = _resolve_handover(state, next_agent, reason)

    # Loop guard: break infinite handover cycles
    visits = dict(state.get("agent_turn_visits") or {})
    visits[res.next_agent] = visits.get(res.next_agent, 0) + 1

    if visits[res.next_agent] > _MAX_VISITS_PER_AGENT and res.next_agent != CONVERSATION:
        logger.warning(
            "Loop guard: %s visited %d times — breaking cycle, redirecting to %s",
            res.next_agent, visits[res.next_agent], CONVERSATION,
        )
        res = HandoverResolution(
            next_agent=CONVERSATION,
            bridge_messages=[SystemMessage(content=(
                "A routing loop was detected. Respond with plain natural language only — "
                "no tool calls. Acknowledge the user's request helpfully."
            ))],
        )
        visits[CONVERSATION] = visits.get(CONVERSATION, 0) + 1

    should_chain = chain or not ai_content

    messages_to_add = (
        ([AIMessage(content=ai_content)] if ai_content else []) + res.bridge_messages
    )

    state_update = {
        "active_agent": res.next_agent,
        "agent_turn_visits": visits,
        "messages": messages_to_add,
    }

    if should_chain:
        # Immediate: next agent responds in the same turn
        logger.info("handle_handover: chaining → %s", res.next_agent)
        return Command(goto=res.next_agent, update=state_update)
    else:
        # Sticky: next agent responds on the next user turn
        logger.info("handle_handover: sticky → %s (responds next turn)", res.next_agent)
        return state_update
