"""Per-turn context (clock + memories) is a TRAILING SystemMessage, and
camera frames are stripped for text-only agents — both KV-cache rules.

Mutating the system prompt per call invalidates the llama.cpp KV-cache
prefix every call; LiveClockMiddleware appends a trailing message instead,
and StripImagesMiddleware keeps image tokens out of text-only agents' slots
(see src/graph/middleware.py).
"""

from dataclasses import dataclass, field, replace
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.graph.middleware import (
    _IMAGE_PLACEHOLDER,
    _strip_image_blocks,
    _time_context,
    _with_clock,
)


@dataclass
class _FakeRequest:
    """Minimal ModelRequest stand-in: .messages, .state and .override()."""

    messages: list = field(default_factory=list)
    state: dict = field(default_factory=dict)

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


def test_clock_is_appended_as_trailing_system_message():
    request = _FakeRequest(messages=[HumanMessage(content="remind me at 5")])
    result = _with_clock(request)

    assert len(result.messages) == 2
    trailing = result.messages[-1]
    assert isinstance(trailing, SystemMessage)
    assert "Current date & time" in trailing.content
    # Original request untouched (override returns a copy).
    assert len(request.messages) == 1


def test_memories_ride_the_trailing_message_not_the_prompt():
    """Recalled memories change every turn — they must live in the trailing
    zone so the static prompt + history prefix stays cached."""
    request = _FakeRequest(
        messages=[HumanMessage(content="what should I eat?")],
        state={"recalled_memories": ["User is vegetarian", "Allergic to peanuts"]},
    )
    trailing = _with_clock(request).messages[-1]
    assert "What you remember about this user" in trailing.content
    assert "User is vegetarian" in trailing.content
    assert "Allergic to peanuts" in trailing.content
    assert "Current date & time" in trailing.content  # clock still there


def test_no_memories_no_memory_header():
    request = _FakeRequest(messages=[HumanMessage(content="hi")])
    trailing = _with_clock(request).messages[-1]
    assert "What you remember" not in trailing.content


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


# ── image stripping ─────────────────────────────────────────────────────────

def _frame_tool_message() -> ToolMessage:
    return ToolMessage(
        tool_call_id="c1",
        name="capture_webcam",
        content=[
            {"type": "text", "text": "Frame captured successfully."},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
        ],
    )


def test_images_stripped_with_stable_placeholder():
    request = _FakeRequest(
        messages=[HumanMessage(content="order what's on the shelf"), _frame_tool_message()]
    )
    result = _strip_image_blocks(request)
    stripped = result.messages[-1]
    assert all(b.get("type") != "image_url" for b in stripped.content)
    assert any(b.get("text") == _IMAGE_PLACEHOLDER for b in stripped.content)
    assert any(b.get("text") == "Frame captured successfully." for b in stripped.content)
    # Original untouched — the conversation agent still sees the real frame.
    assert any(b.get("type") == "image_url" for b in request.messages[-1].content)


def test_no_images_request_returned_unchanged():
    request = _FakeRequest(messages=[HumanMessage(content="plain text")])
    assert _strip_image_blocks(request) is request  # same object, zero copies
