"""Swarm construction: specialist agents with guarded handoffs.

conversation (default) ⇄ swiggy ⇄ instamart ⇄ dineout ⇄ tracker ⇄ planner

Sticky routing is swarm-native: the last active agent receives the next user
turn directly. Handoffs chain within the same turn.
"""

from deepagents import create_deep_agent
from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelRequest,
    dynamic_prompt,
)
from langgraph.graph import StateGraph
from langgraph_swarm import create_swarm

from src.commons.constants import (
    CONVERSATION,
    DINEOUT,
    GATED_TOOL_NAMES,
    INSTAMART,
    PLANNER,
    SWIGGY,
    TRACKER,
)
from src.configs.llm import get_llm
from src.graph.handoff import create_guarded_handoff_tool
from src.graph.middleware import (
    KeepOnlyLatestBridge,
    LiveClockMiddleware,
    ResilientModelMiddleware,
)
from src.graph.state import PlannerAgentState, VisualAgentState, VisualAssistantState
from src.prompts import conversation as conversation_prompt
from src.prompts import dineout as dineout_prompt
from src.prompts import instamart as instamart_prompt
from src.prompts import planner as planner_prompt
from src.prompts import swiggy as swiggy_prompt
from src.prompts import tracker as tracker_prompt


def _make_prompt_middleware(base_prompt: str, mcp_provider: str | None = None,
                            unavailable_note: str = ""):
    # NOTE: recalled memories change once per turn, so the dynamic prompt
    # costs one KV-cache prefill per turn — acceptable. The live clock is
    # deliberately NOT here (it changed per call): LiveClockMiddleware
    # appends it as a trailing message so the prompt prefix stays cached.
    #
    # mcp_provider/unavailable_note: when the agent's MCP provider isn't
    # serving tools (never configured, unreachable, or login expired), the
    # note is appended so the model tells the user instead of flailing with
    # the few non-MCP tools it has left (pi5's provider_ok prompt swap; the
    # swap costs one prefill and only happens on expiry or re-login).
    @dynamic_prompt
    def prompt_with_memories(request: ModelRequest) -> str:
        prompt = base_prompt
        if mcp_provider is not None:
            from src.services.mcp_providers import provider_ok

            if not provider_ok(mcp_provider):
                prompt = prompt + unavailable_note
        memories = request.state.get("recalled_memories") or []
        if memories:
            return (
                prompt
                + "\n\n## What you remember about this user\n"
                + "\n".join(f"- {m}" for m in memories)
            )
        return prompt

    return prompt_with_memories


def _make_agent(name: str, tools: list, base_prompt: str, mcp_provider: str | None = None,
                unavailable_note: str = ""):
    return create_agent(
        # get_llm(name) pins this agent's llama.cpp KV-cache slot (LLM_SLOTS)
        # and applies any per-agent provider/model override.
        model=get_llm(name),
        tools=tools,
        middleware=[
            _make_prompt_middleware(base_prompt, mcp_provider, unavailable_note),
            # Outermost wrap_model_call hook: its retry/fallback re-runs the
            # inner request transforms (bridge pruning, clock).
            ResilientModelMiddleware(),
            KeepOnlyLatestBridge(),
            # Must sit INSIDE KeepOnlyLatestBridge: the clock is a trailing
            # SystemMessage the bridge pruner must never see.
            LiveClockMiddleware(),
            # Gates by tool name, so it's safe to attach to every agent even
            # though SWIGGY_TOOLS/TRACKER_TOOLS are currently the same list
            # object (src/tools/__init__.py) — a gated tool is caught no
            # matter which agent ends up calling it. HumanInTheLoopMiddleware
            # implements aafter_model (delegates to sync after_model), which
            # is required since this graph runs exclusively via astream.
            HumanInTheLoopMiddleware(interrupt_on=GATED_TOOL_NAMES),
        ],
        state_schema=VisualAgentState,
        name=name,
    )


def _make_planner_agent(tools: list, base_prompt: str):
    """Build the planner as a real `deepagents` deep agent.

    Composability with langgraph_swarm was verified in the Phase 0 spike:
    create_deep_agent() returns a CompiledStateGraph with a `tools` node
    langgraph_swarm can inspect for handoff-tool metadata like any other
    agent, so it drops into create_swarm([...]) as a normal peer (no need to
    wrap it as a nested tool). `system_prompt` (not the `dynamic_prompt`
    middleware the other agents use) is the right extension point here — it
    composes in front of deepagents' own default deep-agent prompt (which
    carries the write_todos/task usage instructions) instead of replacing it.
    """
    return create_deep_agent(
        model=get_llm(PLANNER),
        tools=tools,
        system_prompt=base_prompt,
        middleware=[
            ResilientModelMiddleware(),
            KeepOnlyLatestBridge(),
            # The planner's system_prompt is static, so the trailing-message
            # clock is what gives it a live clock at all.
            LiveClockMiddleware(),
            HumanInTheLoopMiddleware(interrupt_on=GATED_TOOL_NAMES),
        ],
        state_schema=PlannerAgentState,
        name=PLANNER,
    )


def build_swarm_graph() -> StateGraph:
    """Build the (uncompiled) swarm StateGraph.

    Must be called AFTER apply_mcp_tools() so MCP tools are in the sets.
    """
    from src.tools import (
        CONVERSATION_TOOLS,
        DINEOUT_TOOLS,
        INSTAMART_TOOLS,
        SWIGGY_TOOLS,
        TRACKER_TOOLS,
    )

    to_conversation = create_guarded_handoff_tool(agent_name=CONVERSATION)
    to_swiggy = create_guarded_handoff_tool(agent_name=SWIGGY)
    to_instamart = create_guarded_handoff_tool(agent_name=INSTAMART)
    to_dineout = create_guarded_handoff_tool(agent_name=DINEOUT)
    to_tracker = create_guarded_handoff_tool(agent_name=TRACKER)
    to_planner = create_guarded_handoff_tool(agent_name=PLANNER)

    conversation = _make_agent(
        CONVERSATION,
        [*CONVERSATION_TOOLS, to_swiggy, to_instamart, to_dineout, to_tracker, to_planner],
        conversation_prompt.build_prompt(),
    )
    swiggy = _make_agent(
        SWIGGY,
        [*SWIGGY_TOOLS, to_instamart, to_dineout, to_tracker, to_conversation, to_planner],
        swiggy_prompt.build_prompt(),
        mcp_provider="swiggy_food",
        unavailable_note=swiggy_prompt.UNAVAILABLE_NOTE,
    )
    instamart = _make_agent(
        INSTAMART,
        [*INSTAMART_TOOLS, to_swiggy, to_dineout, to_tracker, to_conversation, to_planner],
        instamart_prompt.build_prompt(),
        mcp_provider="swiggy_instamart",
        unavailable_note=instamart_prompt.UNAVAILABLE_NOTE,
    )
    dineout = _make_agent(
        DINEOUT,
        [*DINEOUT_TOOLS, to_swiggy, to_instamart, to_conversation, to_planner],
        dineout_prompt.build_prompt(),
        mcp_provider="swiggy_dineout",
        unavailable_note=dineout_prompt.UNAVAILABLE_NOTE,
    )
    tracker = _make_agent(
        TRACKER,
        [*TRACKER_TOOLS, to_swiggy, to_instamart, to_conversation, to_planner],
        tracker_prompt.build_prompt(),
    )
    planner = _make_planner_agent(
        [to_conversation, to_swiggy, to_instamart, to_dineout, to_tracker],
        planner_prompt.build_prompt(),
    )

    return create_swarm(
        [conversation, swiggy, instamart, dineout, tracker, planner],
        default_active_agent=CONVERSATION,
        state_schema=VisualAssistantState,
    )
