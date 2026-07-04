"""State schemas for the swarm graph and its agents."""

from typing import Optional

from langchain.agents import AgentState
from langgraph_swarm import SwarmState


class VisualAssistantState(SwarmState):
    """Top-level swarm state (messages + active_agent from SwarmState)."""

    always_speak: Optional[bool]
    # Loop guard: per-turn handoff count per agent; reset to {} in each /chat input
    agent_turn_visits: dict
    # Mem0 recall results injected once per turn (Phase 4)
    recalled_memories: list


class VisualAgentState(AgentState):
    """Per-agent (react subgraph) state — shares the swarm's extra channels."""

    agent_turn_visits: dict
    recalled_memories: list
