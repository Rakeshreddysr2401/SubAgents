"""The live clock arrives as a TRAILING SystemMessage, not a prompt edit.

Mutating the system prompt per model call invalidates the llama.cpp KV-cache
prefix every call; LiveClockMiddleware appends a one-line trailing message
instead (see src/graph/middleware.py).
"""

from dataclasses import dataclass, field, replace
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.middleware import _time_context, _with_clock


@dataclass
class _FakeRequest:
    """Minimal ModelRequest stand-in: just .messages and .override()."""

    messages: list = field(default_factory=list)

    def override(self, **overrides):
        return replace(self, **overrides)


def test_time_context_carries_todays_date():
    today = datetime.now().astimezone().date().isoformat()
    context = _time_context()
    assert today in context
    assert "Current date & time" in context


def test_time_context_is_minute_stable():
    """Rounded to the minute so retries within a minute are byte-identical
    (identical requests can reuse the llama.cpp KV-cache prefix)."""
    import time

    first = _time_context()
    time.sleep(0.002)
    second = _time_context()
    assert first == second
    assert ":00+" in first or first.endswith(")")  # seconds zeroed out


def test_clock_is_appended_as_trailing_system_message():
    request = _FakeRequest(messages=[HumanMessage(content="remind me at 5")])
    result = _with_clock(request)

    assert len(result.messages) == 2
    trailing = result.messages[-1]
    assert isinstance(trailing, SystemMessage)
    assert "Current date & time" in trailing.content
    # Original request untouched (override returns a copy).
    assert len(request.messages) == 1


def test_clock_never_pruned_as_stale_bridge():
    """Bridge pruning keeps only the LAST SystemMessage in history — the clock
    must be appended after pruning runs (middleware ordering), so pruning a
    clock-carrying request must never drop a real handoff bridge."""
    from src.graph.middleware import _prune_stale_bridges

    bridge = SystemMessage(content="You are now the swiggy agent")
    request = _FakeRequest(
        messages=[SystemMessage(content="stale bridge"), HumanMessage(content="hi"), bridge]
    )
    pruned = _prune_stale_bridges(request)
    assert bridge in pruned.messages
    assert all(
        m.content != "stale bridge" for m in pruned.messages if isinstance(m, SystemMessage)
    )
    # Clock goes on AFTER pruning: last message is the clock, bridge survives.
    final = _with_clock(pruned)
    assert "Current date & time" in final.messages[-1].content
    assert bridge in final.messages
