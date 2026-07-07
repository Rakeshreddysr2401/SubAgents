"""Agents get a live clock in their dynamic prompt (needed for reminders)."""

from datetime import datetime

from src.graph.swarm import _time_context


def test_time_context_carries_todays_date():
    today = datetime.now().astimezone().date().isoformat()
    context = _time_context()
    assert today in context
    assert "Current date & time" in context


def test_time_context_is_fresh_per_call():
    """The clock must be evaluated per call, not captured once at import."""
    import time

    first = _time_context()
    time.sleep(0.002)  # isoformat carries microseconds — any sleep separates them
    second = _time_context()
    assert first != second
