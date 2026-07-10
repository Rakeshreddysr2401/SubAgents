"""ResilientModelMiddleware: cooldown, fallback routing, degraded replies."""

from dataclasses import dataclass, field, replace

import pytest

from src.configs.settings import get_settings
from src.graph.middleware import (
    DEGRADED_ERROR_REPLY,
    DEGRADED_OFFLINE_REPLY,
    ResilientModelMiddleware,
)
from src.services import llm_registry


@dataclass
class _FakeRequest:
    model: object = None
    messages: list = field(default_factory=list)

    def override(self, **overrides):
        return replace(self, **overrides)


class _FakeResponse:
    def __init__(self, tag: str):
        self.tag = tag


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    llm_registry.reset_health()
    get_settings.cache_clear()
    yield
    llm_registry.reset_health()
    get_settings.cache_clear()


def _with_fallback(monkeypatch):
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "openai")
    monkeypatch.setenv("FALLBACK_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("FALLBACK_LLM_API_KEY", "sk-test")
    get_settings.cache_clear()


def _without_fallback(monkeypatch):
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "")
    monkeypatch.setenv("FALLBACK_LLM_MODEL", "")
    get_settings.cache_clear()


async def test_success_passthrough(monkeypatch):
    _without_fallback(monkeypatch)
    mw = ResilientModelMiddleware()

    async def handler(request):
        return _FakeResponse("primary")

    result = await mw.awrap_model_call(_FakeRequest(model="primary"), handler)
    assert result.tag == "primary"
    assert llm_registry.primary_available()


async def test_connection_error_retries_then_degrades_without_fallback(monkeypatch):
    _without_fallback(monkeypatch)
    mw = ResilientModelMiddleware()
    calls = []

    async def handler(request):
        calls.append(request.model)
        raise ConnectionError("refused")

    result = await mw.awrap_model_call(_FakeRequest(model="primary"), handler)
    assert len(calls) == 2  # one visible retry on the primary, nothing else
    assert result.result[0].content == DEGRADED_OFFLINE_REPLY
    assert not llm_registry.primary_available()  # cooldown armed


async def test_connection_error_falls_back(monkeypatch):
    _with_fallback(monkeypatch)
    mw = ResilientModelMiddleware()
    calls = []

    async def handler(request):
        calls.append(request.model)
        if request.model == "primary":
            raise ConnectionError("refused")
        return _FakeResponse("fallback")

    result = await mw.awrap_model_call(_FakeRequest(model="primary"), handler)
    assert result.tag == "fallback"
    assert calls[:2] == ["primary", "primary"]  # retry before giving up
    assert calls[2] != "primary"  # fallback model was swapped in
    assert not llm_registry.primary_available()


async def test_cooldown_skips_primary_entirely(monkeypatch):
    _with_fallback(monkeypatch)
    llm_registry.report_primary_failure()  # already in cooldown
    mw = ResilientModelMiddleware()
    calls = []

    async def handler(request):
        calls.append(request.model)
        return _FakeResponse("fallback")

    result = await mw.awrap_model_call(_FakeRequest(model="primary"), handler)
    assert result.tag == "fallback"
    assert calls != ["primary"]  # primary never tried
    assert len(calls) == 1


async def test_request_error_no_fallback_attempted(monkeypatch):
    _with_fallback(monkeypatch)
    mw = ResilientModelMiddleware()
    calls = []

    async def handler(request):
        calls.append(request.model)
        raise ValueError("bad request shape")

    result = await mw.awrap_model_call(_FakeRequest(model="primary"), handler)
    assert calls == ["primary"]  # no retry, no fallback — it would fail too
    assert result.result[0].content == DEGRADED_ERROR_REPLY
    assert llm_registry.primary_available()  # request errors don't arm cooldown


async def test_both_dead_returns_degraded(monkeypatch):
    _with_fallback(monkeypatch)
    mw = ResilientModelMiddleware()

    async def handler(request):
        raise ConnectionError("everything is down")

    result = await mw.awrap_model_call(_FakeRequest(model="primary"), handler)
    assert result.result[0].content == DEGRADED_OFFLINE_REPLY


async def test_interrupt_propagates(monkeypatch):
    """HITL interrupts must never be swallowed into a degraded reply."""
    from langgraph.errors import GraphInterrupt

    _without_fallback(monkeypatch)
    mw = ResilientModelMiddleware()

    async def handler(request):
        raise GraphInterrupt()

    with pytest.raises(GraphInterrupt):
        await mw.awrap_model_call(_FakeRequest(model="primary"), handler)


def test_sync_wrap_model_call_mirrors_async(monkeypatch):
    """The graph runs via astream, but the sync hook must work too."""
    _with_fallback(monkeypatch)
    mw = ResilientModelMiddleware()
    calls = []

    def handler(request):
        calls.append(request.model)
        if request.model == "primary":
            raise ConnectionError("refused")
        return _FakeResponse("fallback")

    result = mw.wrap_model_call(_FakeRequest(model="primary"), handler)
    assert result.tag == "fallback"
    assert not llm_registry.primary_available()
