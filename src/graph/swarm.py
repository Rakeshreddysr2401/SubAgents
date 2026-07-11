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
    SummarizationMiddleware,
    dynamic_prompt,
)
from langgraph.graph import StateGraph
from langgraph_swarm import create_swarm

from src.configs.settings import get_settings

from src.commons.constants import CONVERSATION, GATED_TOOL_NAMES, PLANNER
from src.configs.llm import get_llm, get_utility_llm
from src.graph.handoff import create_guarded_handoff_tool
from src.graph.middleware import (
    KeepOnlyLatestBridge,
    LiveClockMiddleware,
    ResilientModelMiddleware,
    StripImagesMiddleware,
)
from src.graph.registry import AGENT_SPECS
from src.graph.state import PlannerAgentState, VisualAgentState, VisualAssistantState


def _make_prompt_middleware(base_prompt: str, mcp_provider: str | None = None,
                            unavailable_note=None):
    # KV-cache discipline: the prompt must be STATIC across turns — anything
    # per-turn (recalled memories, the live clock) goes into the trailing
    # message appended by LiveClockMiddleware instead, so the prompt + history
    # prefix stays cached in the agent's llama.cpp slot.
    #
    # mcp_provider/unavailable_note is the only dynamic part: when the agent's
    # MCP provider isn't serving tools, a reason-aware note is appended
    # (not_connected vs expired) so the model tells the user honestly instead
    # of flailing with the few non-MCP tools it has left. Only two distinct
    # prompt strings ever exist per agent, so the swap costs one re-prefill and
    # only fires on connect/expiry.
    @dynamic_prompt
    def agent_prompt(request: ModelRequest) -> str:
        if mcp_provider is not None and unavailable_note is not None:
            from src.services.mcp_providers import provider_unavailable_reason

            reason = provider_unavailable_reason(mcp_provider)
            if reason is not None:
                return base_prompt + unavailable_note(reason)
        return base_prompt

    return agent_prompt


def _summarization_middleware() -> SummarizationMiddleware | None:
    """Long-thread compaction — the biggest reliability lever for small local
    context windows. Uses the cheap utility model; a summarization event
    rewrites history (one full slot re-prefill), which is rare and worth it.
    """
    s = get_settings()
    if s.summarization_trigger_tokens <= 0:
        return None
    return SummarizationMiddleware(
        model=get_utility_llm(),
        trigger=("tokens", s.summarization_trigger_tokens),
        keep=("messages", s.summarization_keep_messages),
    )


def _make_agent(name: str, tools: list, base_prompt: str, mcp_provider: str | None = None,
                unavailable_note: str = "", vision: bool = False):
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
            *([mw] if (mw := _summarization_middleware()) else []),
            KeepOnlyLatestBridge(),
            # Text-only agents never pay camera-frame token costs in their
            # KV slots; the conversation agent keeps the real images.
            *([] if vision else [StripImagesMiddleware()]),
            # Must sit INSIDE KeepOnlyLatestBridge: the trailing per-turn
            # context (memories + clock) must never look like a bridge.
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
    subagents = _planner_subagents()
    if subagents:
        base_prompt = base_prompt + (
            "\n\nFor research-heavy steps (comparing options, gathering facts, "
            "reading the user's documents), use your task tool to delegate to "
            "the `research` subagent instead of researching in this thread — "
            "it returns a concise brief without bloating your context."
        )
    return create_deep_agent(
        model=get_llm(PLANNER),
        tools=tools,
        system_prompt=base_prompt,
        subagents=subagents or None,
        middleware=[
            ResilientModelMiddleware(),
            # NO SummarizationMiddleware here: deepagents injects its own —
            # adding ours trips create_agent's duplicate-middleware check.
            KeepOnlyLatestBridge(),
            StripImagesMiddleware(),  # the planner is text-only too
            # The planner's system_prompt is static, so the trailing-message
            # context (memories + clock) is what gives it a live clock at all.
            LiveClockMiddleware(),
            HumanInTheLoopMiddleware(interrupt_on=GATED_TOOL_NAMES),
        ],
        state_schema=PlannerAgentState,
        name=PLANNER,
    )


def _planner_subagents() -> list[dict]:
    """deepagents subagents for the planner's built-in `task` tool.

    `research` runs on the cheap utility model with web + document search, so
    planner research doesn't burn main-model context. Registered only when
    web search is configured (its whole value is fresh information).
    """
    if not get_settings().tavily_api_key:
        return []
    from src.rag.retrieval_tools import search_documents
    from src.rag.web_cache import cached_web_search

    return [
        {
            "name": "research",
            "description": (
                "Researches a question using web search and the user's uploaded "
                "documents, returning a concise factual brief with sources."
            ),
            "system_prompt": (
                "You are a research assistant. Answer the question you're given "
                "using cached_web_search and search_documents. Be thorough in "
                "gathering, then respond with a CONCISE brief: key facts, "
                "numbers, and source names only — no filler."
            ),
            "tools": [cached_web_search, search_documents],
            "model": get_utility_llm(),
        }
    ]


def build_swarm_graph() -> StateGraph:
    """Build the (uncompiled) swarm StateGraph from AGENT_SPECS.

    Everything — agents, tool sets, handoff wiring — derives from the
    registry (src/graph/registry.py); this function has no per-agent
    knowledge. Must be called AFTER apply_mcp_tools() so the MCP tools are
    in the (late-bound) tool lists.
    """
    handoffs = {
        name: create_guarded_handoff_tool(agent_name=name) for name in AGENT_SPECS
    }

    agents = []
    for name, spec in AGENT_SPECS.items():
        transfers = [
            handoffs[peer]
            for peer in AGENT_SPECS
            if peer != name and peer not in spec.no_handoff_to
        ]
        prompt = spec.prompt_module.build_prompt()
        if spec.deep:
            agents.append(_make_planner_agent([*spec.tools(), *transfers], prompt))
        else:
            agents.append(_make_agent(
                name,
                [*spec.tools(), *transfers],
                prompt,
                mcp_provider=spec.mcp_provider,
                unavailable_note=getattr(spec.prompt_module, "unavailable_note", None),
                vision=spec.vision,
            ))

    return create_swarm(
        agents,
        default_active_agent=CONVERSATION,
        state_schema=VisualAssistantState,
    )
