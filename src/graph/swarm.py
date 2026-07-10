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

from src.commons.constants import (
    CONVERSATION,
    DINEOUT,
    GATED_TOOL_NAMES,
    INSTAMART,
    PLANNER,
    SWIGGY,
    TRACKER,
)
from src.configs.llm import get_llm, get_utility_llm
from src.graph.handoff import create_guarded_handoff_tool
from src.graph.middleware import (
    KeepOnlyLatestBridge,
    LiveClockMiddleware,
    ResilientModelMiddleware,
    StripImagesMiddleware,
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
    # KV-cache discipline: the prompt must be STATIC across turns — anything
    # per-turn (recalled memories, the live clock) goes into the trailing
    # message appended by LiveClockMiddleware instead, so the prompt + history
    # prefix stays cached in the agent's llama.cpp slot.
    #
    # mcp_provider/unavailable_note is the only dynamic part: when the agent's
    # MCP provider isn't serving tools (never configured, unreachable, or
    # login expired), the note is appended so the model tells the user instead
    # of flailing with the few non-MCP tools it has left (pi5's provider_ok
    # prompt swap; it costs one re-prefill and only fires on expiry/re-login).
    @dynamic_prompt
    def agent_prompt(request: ModelRequest) -> str:
        if mcp_provider is not None:
            from src.services.mcp_providers import provider_ok

            if not provider_ok(mcp_provider):
                return base_prompt + unavailable_note
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
        vision=True,  # the only agent that sees camera frames
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
