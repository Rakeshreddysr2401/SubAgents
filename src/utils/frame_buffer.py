"""In-memory buffer for the absolute latest video frame, keyed by thread_id.

Frames are base64-encoded JPEG strings sent from the browser via WebSocket.
Only the most recent frame per thread is retained.
"""

import threading
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()

# thread_id -> latest base64_jpeg: str
_latest_frames: dict[str, str] = {}


def store_frame(thread_id: str, base64_jpeg: str) -> None:
    """Store the absolute latest frame for a thread."""
    with _lock:
        _latest_frames[thread_id] = base64_jpeg


def get_latest_frame(thread_id: str) -> str | None:
    """Return the latest frame (base64 string) or None if none exist."""
    with _lock:
        return _latest_frames.get(thread_id)


def clear_frames(thread_id: str) -> None:
    """Remove the stored frame for a thread."""
    with _lock:
        _latest_frames.pop(thread_id, None)


def has_frames(thread_id: str) -> bool:
    """Check whether any frame exists for a thread."""
    with _lock:
        return thread_id in _latest_frames


def get_all_thread_ids() -> list[str]:
    """Return a snapshot of all thread IDs that have a buffered frame."""
    with _lock:
        return list(_latest_frames.keys())
