from typing import NamedTuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from src.configs.logging_config import get_logger
from src.states.states import AgentState
from src.tools.handover_tool import HANDOVER_NAMES

logger = get_logger(__name__)

_MAX_VISITS_PER_AGENT = 3
SUB_AGENTS = {"conversation", "swiggy", "tracker"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_handover(content: str) -> tuple[str, str, bool]:
    parts = content.split("|", 2)
    agent = parts[0].strip()
    reason = parts[1].strip() if len(parts) > 1 else ""
    chain = parts[2].strip().lower() == "true" if len(parts) > 2 else False
    return agent, reason, chain


def _extract_handover_context(state: AgentState) -> tuple[str, str, str]:
    """Return (next_agent, reason, ai_content) from the most recent handover."""
    next_agent = reason = ai_content = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.name in HANDOVER_NAMES:
            next_agent, reason, _ = parse_handover(msg.content)
        elif isinstance(msg, AIMessage):
            ai_content = msg.content
            break
    return next_agent, reason, ai_content


def _last_user_query(state: AgentState) -> str:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

class HandoverResolution(NamedTuple):
    next_agent: str
    state_updates: dict
    bridge_messages: list


_AGENT_DESCRIPTIONS = {
    "conversation": "general queries, web search, system info, and visual questions via webcam",
    "swiggy": "food ordering, restaurant search, cart management, and placing Swiggy orders",
    "tracker": "tracking active Swiggy orders and checking delivery status",
    "supervisor": "routing user requests to the appropriate agent",
}


def _resolve_handover(state: AgentState, raw_next_agent: str, reason: str) -> HandoverResolution:
    current = state.get("active_agent", "supervisor")
    user_query = _last_user_query(state)

    # Sub-agent adapter: sub-agents can only route to supervisor, not each other.
    next_agent = raw_next_agent
    if current in SUB_AGENTS and next_agent in SUB_AGENTS:
        logger.info("Adapter: %s tried to route to %s — overriding to supervisor", current, next_agent)
        next_agent = "supervisor"

    bridge_content: str | None = None

    if next_agent == "supervisor":
        if reason == "cannot_answer":
            bridge_content = (
                f"The previous agent ('{current}') could not answer the user's question. "
                f"Do NOT route back to '{current}'. Try a different agent.\n"
                f"The user asked: \"{user_query}\""
            )
        else:
            bridge_content = "Route to the appropriate agent based on the conversation."
    else:
        desc = _AGENT_DESCRIPTIONS.get(next_agent, next_agent)
        bridge_content = (
            f"You are the {next_agent} agent, responsible for: {desc}.\n"
            f"You were called because: \"{reason or 'user request'}\". "
            f"The user said: \"{user_query}\". "
            f"Handle this directly without re-asking what was already provided."
        )

    logger.info("Handover resolved: %s → %s (reason: %s)", current, next_agent, reason or "normal")
    return HandoverResolution(
        next_agent=next_agent,
        state_updates={},
        bridge_messages=[SystemMessage(content=bridge_content)] if bridge_content else [],
    )


def _respond_with_handover(state: AgentState, label: str) -> dict:
    next_agent, reason, ai_content = _extract_handover_context(state)
    if not next_agent:
        logger.warning("%s: no handover tool message found", label)
        return {}
    res = _resolve_handover(state, next_agent, reason)
    msgs = ([AIMessage(content=ai_content)] if ai_content else []) + res.bridge_messages
    logger.info("%s → %s (text: %.80s)", label, res.next_agent, ai_content)
    return {"active_agent": res.next_agent, **res.state_updates, "messages": msgs}


# ---------------------------------------------------------------------------
# Three handover handler nodes
# ---------------------------------------------------------------------------

def apply_handover(state: AgentState) -> Command:
    """Type 1 — Silent transfer: no text from current agent, next agent responds immediately."""
    next_agent, reason, _ = _extract_handover_context(state)
    if not next_agent:
        logger.warning("apply_handover: no handover tool message found")
        return Command(goto="supervisor", update={})

    res = _resolve_handover(state, next_agent, reason)

    # Loop guard: break infinite handover cycles
    visits = dict(state.get("agent_turn_visits") or {})
    visits[res.next_agent] = visits.get(res.next_agent, 0) + 1

    if visits[res.next_agent] > _MAX_VISITS_PER_AGENT and res.next_agent != "conversation":
        logger.warning(
            "Loop guard: %s visited %d times — breaking cycle, redirecting to conversation",
            res.next_agent, visits[res.next_agent],
        )
        res = HandoverResolution(
            next_agent="conversation",
            state_updates={},
            bridge_messages=[SystemMessage(content=(
                "A routing loop was detected. Respond with plain natural language only — "
                "no tool calls. Acknowledge the user's request helpfully. If you cannot help, "
                "say: 'I'm not sure how to help with that. Could you rephrase your question?'"
            ))],
        )
        visits["conversation"] = visits.get("conversation", 0) + 1

    return Command(goto=res.next_agent, update={
        "active_agent": res.next_agent,
        **res.state_updates,
        "agent_turn_visits": visits,
        "messages": res.bridge_messages,
    })


def respond_then_wait(state: AgentState) -> dict:
    """Type 2 — Respond then wait: current agent responds, next agent picks up on the next human turn."""
    return _respond_with_handover(state, "respond_then_wait")


def respond_and_chain(state: AgentState) -> Command:
    """Type 3 — Respond and chain: current agent responds AND next agent responds immediately."""
    result = _respond_with_handover(state, "respond_and_chain")
    next_agent = result.get("active_agent", "supervisor")
    return Command(goto=next_agent, update=result)
