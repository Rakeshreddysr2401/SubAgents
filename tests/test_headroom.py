"""Phase-5 features: summarization config, progress emitter, guardian verdict,
planner research subagent registration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.configs.settings import get_settings


@pytest.fixture(autouse=True)
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ── summarization middleware factory ────────────────────────────────────────

def test_summarization_enabled_by_default(monkeypatch):
    from src.graph.swarm import _summarization_middleware

    mw = _summarization_middleware()
    assert mw is not None


def test_summarization_disabled_with_zero_trigger(monkeypatch):
    from src.graph.swarm import _summarization_middleware

    monkeypatch.setenv("SUMMARIZATION_TRIGGER_TOKENS", "0")
    get_settings.cache_clear()
    assert _summarization_middleware() is None


# ── progress emitter ────────────────────────────────────────────────────────

def test_emit_progress_noop_outside_graph():
    from src.tools.progress import emit_progress

    emit_progress("should not raise outside a graph run")


async def test_progress_flows_through_custom_stream():
    """A node emitting via get_stream_writer surfaces on the custom channel —
    the exact payload shape chat.py maps to the {"progress": ...} SSE event."""
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    class S(TypedDict):
        x: int

    def node(state: S):
        from src.tools.progress import emit_progress

        emit_progress("halfway there")
        return {"x": 1}

    g = StateGraph(S)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    compiled = g.compile()

    custom_payloads = []
    async for mode, payload in compiled.astream({"x": 0}, stream_mode=["custom", "updates"]):
        if mode == "custom":
            custom_payloads.append(payload)
    assert {"progress": "halfway there"} in custom_payloads


# ── guardian structured verdict ─────────────────────────────────────────────

async def test_guardian_verdict_structured_path():
    from src.services.guardian import GuardianVerdict, _get_verdict

    llm = MagicMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(
        return_value=GuardianVerdict(observation="a calm room", concern=False)
    )
    llm.with_structured_output = MagicMock(return_value=structured)

    verdict = await _get_verdict(llm, MagicMock())
    assert verdict == {"observation": "a calm room", "concern": False, "message": ""}
    llm.ainvoke.assert_not_called()  # no fallback needed


async def test_guardian_verdict_falls_back_to_json_parse():
    from src.services.guardian import _get_verdict

    llm = MagicMock()
    llm.with_structured_output = MagicMock(side_effect=NotImplementedError("no schema"))
    reply = MagicMock()
    reply.content = '{"observation": "smoke near stove", "concern": true, "message": "Check the stove!"}'
    llm.ainvoke = AsyncMock(return_value=reply)

    verdict = await _get_verdict(llm, MagicMock())
    assert verdict["concern"] is True
    assert verdict["message"] == "Check the stove!"


# ── planner research subagent ───────────────────────────────────────────────

def test_research_subagent_only_with_tavily(monkeypatch):
    from src.graph.swarm import _planner_subagents

    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    assert _planner_subagents() == []

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    get_settings.cache_clear()
    subagents = _planner_subagents()
    assert len(subagents) == 1
    assert subagents[0]["name"] == "research"
    tool_names = [t.name for t in subagents[0]["tools"]]
    assert "cached_web_search" in tool_names
    assert "search_documents" in tool_names
