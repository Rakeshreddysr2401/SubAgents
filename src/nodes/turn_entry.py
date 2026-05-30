"""turn_entry — runs at the start of every user turn.

Resets per-turn state (loop guard) and routes either to the sticky active agent
or to the supervisor for fresh routing.
"""

from langgraph.types import Command

from src.commons.constants import SUPERVISOR
from src.configs.logging_config import get_logger
from src.states.states import AgentState

logger = get_logger(__name__)

# Agents that persist across turns (skip supervisor re-routing when active)
_STICKY_AGENTS = set()  # Extend if specific agents should be sticky in the future


def turn_entry_node(state: AgentState) -> Command:
    active = state.get("active_agent", "")

    # Reset per-turn loop guard counters
    updates = {"agent_turn_visits": {}}

    next_node = active if active in _STICKY_AGENTS else SUPERVISOR
    logger.debug("turn_entry: active_agent=%s → routing to %s", active or "(none)", next_node)

    return Command(goto=next_node, update=updates)
