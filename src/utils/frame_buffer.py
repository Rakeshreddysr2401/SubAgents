"""In-memory rolling buffer for video frames, keyed by thread_id.

Frames are base64-encoded JPEG strings sent from the browser via WebSocket.
The buffer keeps the latest N frames per thread for on-demand retrieval
by LangGraph agents.
"""

import threading
from collections import deque

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

_MAX_FRAMES = 5
_lock = threading.Lock()
_buffers: dict[str, deque] = {}


def store_frame(thread_id: str, base64_jpeg: str) -> None:
    """Append a frame to the thread's rolling buffer."""
    with _lock:
        if thread_id not in _buffers:
            _buffers[thread_id] = deque(maxlen=_MAX_FRAMES)
        _buffers[thread_id].append(base64_jpeg)


def get_latest_frames(thread_id: str, count: int = 1) -> list[str]:
    """Return the latest `count` frames for a thread (newest last).

    Returns an empty list if no frames are available.
    """
    with _lock:
        buf = _buffers.get(thread_id)
        if not buf:
            return []
        # Slice the last `count` items from the deque
        frames = list(buf)[-count:]
        return frames


def clear_frames(thread_id: str) -> None:
    """Remove all stored frames for a thread."""
    with _lock:
        _buffers.pop(thread_id, None)


def has_frames(thread_id: str) -> bool:
    """Check whether any frames exist for a thread."""
    with _lock:
        buf = _buffers.get(thread_id)
        return bool(buf)
