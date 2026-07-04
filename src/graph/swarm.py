"""Swarm construction: three specialist agents with guarded handoffs.

conversation (default) ⇄ swiggy ⇄ tracker

Sticky routing is swarm-native: the last active agent receives the next user
turn directly. Handoffs chain within the same turn.
"""

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, dynamic_prompt
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph
from langgraph_swarm import create_swarm

from src.commons.constants import CONVERSATION, SWIGGY, TRACKER
from src.configs.llm import get_llm
from src.graph.handoff import create_guarded_handoff_tool
from src.graph.state import VisualAgentState, VisualAssistantState
from src.prompts import conversation as conversation_prompt
from src.prompts import swiggy as swiggy_prompt
from src.prompts import tracker as tracker_prompt


def _prune_stale_bridges(request: ModelRequest) -> ModelRequest:
    """Drop stale handoff-bridge SystemMessages from history.

    Bridges are the only SystemMessages inside `messages` (the agent's own
    system prompt travels separately). Old bridges from earlier turns would
    tell the model it is a *different* agent — keep only the most recent one.
    """
    system_indices = [
        i for i, m in enumerate(request.messages) if isinstance(m, SystemMessage)
    ]
    if len(system_indices) > 1:
        stale = set(system_indices[:-1])
        pruned = [m for i, m in enumerate(request.messages) if i not in stale]
        return request.override(messages=pruned)
    return request


class KeepOnlyLatestBridge(AgentMiddleware):
    """Prune stale handoff-bridge SystemMessages (sync + async)."""

    def wrap_model_call(self, request, handler):
        return handler(_prune_stale_bridges(request))

    async def awrap_model_call(self, request, handler):
        return await handler(_prune_stale_bridges(request))


def _make_prompt_middleware(base_prompt: str):
    @dynamic_prompt
    def prompt_with_memories(request: ModelRequest) -> str:
        memories = request.state.get("recalled_memories") or []
        if memories:
            return (
                base_prompt
                + "\n\n## What you remember about this user\n"
                + "\n".join(f"- {m}" for m in memories)
            )
        return base_prompt

    return prompt_with_memories


def _make_agent(name: str, tools: list, base_prompt: str):
    return create_agent(
        model=get_llm(),
        tools=tools,
        middleware=[_make_prompt_middleware(base_prompt), KeepOnlyLatestBridge()],
        state_schema=VisualAgentState,
        name=name,
    )


def build_swarm_graph() -> StateGraph:
    """Build the (uncompiled) swarm StateGraph.

    Must be called AFTER apply_swiggy_tools() so MCP tools are in the sets.
    """
    from src.tools import CONVERSATION_TOOLS, SWIGGY_TOOLS, TRACKER_TOOLS

    to_conversation = create_guarded_handoff_tool(agent_name=CONVERSATION)
    to_swiggy = create_guarded_handoff_tool(agent_name=SWIGGY)
    to_tracker = create_guarded_handoff_tool(agent_name=TRACKER)

    conversation = _make_agent(
        CONVERSATION,
        [*CONVERSATION_TOOLS, to_swiggy, to_tracker],
        conversation_prompt.build_prompt(),
    )
    swiggy = _make_agent(
        SWIGGY,
        [*SWIGGY_TOOLS, to_tracker, to_conversation],
        swiggy_prompt.build_prompt(),
    )
    tracker = _make_agent(
        TRACKER,
        [*TRACKER_TOOLS, to_swiggy, to_conversation],
        tracker_prompt.build_prompt(),
    )

    return create_swarm(
        [conversation, swiggy, tracker],
        default_active_agent=CONVERSATION,
        state_schema=VisualAssistantState,
    )
