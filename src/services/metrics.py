"""In-process counters/gauges + Prometheus text rendering.

Deliberately dependency-free (no prometheus_client): a handful of atomic
counters is all a single-process assistant needs, and the render format is
stable. Exposed at GET /metrics behind METRICS_TOKEN (src/api/system.py).
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_counters: dict[str, int] = {}
_gauges: dict[str, float] = {}

# Names double as documentation of what we instrument.
COUNTERS = (
    "chat_turns_total",
    "chat_errors_total",
    "interrupts_total",
    "llm_primary_failures_total",
    "llm_fallback_used_total",
    "mcp_tool_failures_total",
)
GAUGES = (
    "llm_primary_up",
    "sse_clients",
)


def inc(name: str, by: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + by


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[name] = value


def adjust_gauge(name: str, delta: float) -> None:
    with _lock:
        _gauges[name] = _gauges.get(name, 0) + delta


def snapshot() -> dict:
    with _lock:
        return {"counters": dict(_counters), "gauges": dict(_gauges)}


def reset() -> None:
    """Test seam."""
    with _lock:
        _counters.clear()
        _gauges.clear()


def render_prometheus() -> str:
    """Prometheus text exposition format, all metrics namespaced subagents_*."""
    lines: list[str] = []
    with _lock:
        for name in COUNTERS:
            lines.append(f"# TYPE subagents_{name} counter")
            lines.append(f"subagents_{name} {_counters.get(name, 0)}")
        for name in GAUGES:
            lines.append(f"# TYPE subagents_{name} gauge")
            lines.append(f"subagents_{name} {_gauges.get(name, 0)}")
    return "\n".join(lines) + "\n"
