"""In-memory rolling buffer for video frames, keyed by thread_id.

Frames are base64-encoded JPEG strings sent from the browser via WebSocket.
Each frame is stored with a unix timestamp to support time-range queries.

Retention: frames older than _WINDOW_SECONDS are evicted automatically.
"""

import threading
import time
from collections import deque

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

_WINDOW_SECONDS = 300   # 5-minute rolling window
_lock = threading.Lock()

# thread_id -> deque of (timestamp: float, base64_jpeg: str)
_buffers: dict[str, deque] = {}


def store_frame(thread_id: str, base64_jpeg: str) -> None:
    """Append a timestamped frame and evict frames outside the 5-min window."""
    now = time.time()
    cutoff = now - _WINDOW_SECONDS
    with _lock:
        if thread_id not in _buffers:
            _buffers[thread_id] = deque()
        _buffers[thread_id].append((now, base64_jpeg))
        # Evict from the left while oldest frame is outside the window
        while _buffers[thread_id] and _buffers[thread_id][0][0] < cutoff:
            _buffers[thread_id].popleft()


def get_latest_frames(thread_id: str, count: int = 1) -> list[str]:
    """Return the latest `count` frames (base64 strings, newest last)."""
    with _lock:
        buf = _buffers.get(thread_id)
        if not buf:
            return []
        items = list(buf)[-count:]
    return [b64 for _, b64 in items]


def get_frames_in_range(thread_id: str, start: float, end: float) -> list[tuple[float, str]]:
    """Return (timestamp, base64) pairs for frames within [start, end]."""
    with _lock:
        buf = _buffers.get(thread_id)
        if not buf:
            return []
        return [(ts, b64) for ts, b64 in buf if start <= ts <= end]


def get_frames_last_n_seconds(thread_id: str, seconds: int = 30) -> list[str]:
    """Return base64 frames from the last `seconds` seconds (oldest first)."""
    cutoff = time.time() - seconds
    with _lock:
        buf = _buffers.get(thread_id)
        if not buf:
            return []
        return [b64 for ts, b64 in buf if ts >= cutoff]


def clear_frames(thread_id: str) -> None:
    """Remove all stored frames for a thread."""
    with _lock:
        _buffers.pop(thread_id, None)


def has_frames(thread_id: str) -> bool:
    """Check whether any frames exist for a thread."""
    with _lock:
        buf = _buffers.get(thread_id)
        return bool(buf)


def frame_count(thread_id: str) -> int:
    """Return number of frames currently buffered for a thread."""
    with _lock:
        buf = _buffers.get(thread_id)
        return len(buf) if buf else 0


def get_all_thread_ids() -> list[str]:
    """Return a snapshot of all thread IDs that have buffered frames."""
    with _lock:
        return list(_buffers.keys())
