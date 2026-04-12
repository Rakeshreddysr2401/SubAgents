"""Frame store — simplified, no CLIP, no numpy, no torch.

The original store ran CLIP (PyTorch + open_clip) on every motion-triggered
frame to produce 512-dim embeddings. On a laptop this caused high RAM usage
and slow startup.

Now it's a thin delegate to frame_buffer. Frames are already stored there;
this class just provides the same interface so existing imports still work.
"""

import time
from dataclasses import dataclass

from src.configs.logging_config import get_logger
from src.utils.frame_buffer import (
    get_frames_in_range,
    get_frames_last_n_seconds,
)

logger = get_logger(__name__)

_WINDOW_SECONDS = 300  # 5-minute rolling window


@dataclass
class StoredFrame:
    timestamp: float
    thread_id: str
    b64_jpeg: str


class FrameStore:
    """Thin wrapper around frame_buffer — no CLIP, no numpy, no torch."""

    def store(self, thread_id: str, b64_jpeg: str, timestamp: float | None = None) -> StoredFrame:
        # frame_buffer already stores every frame from webapp.py — this is a no-op.
        ts = timestamp or time.time()
        return StoredFrame(timestamp=ts, thread_id=thread_id, b64_jpeg=b64_jpeg)

    def search(
        self,
        thread_id: str,
        query: str,
        top_k: int = 3,
        time_start: float | None = None,
        time_end: float | None = None,
    ) -> list[StoredFrame]:
        """Return up to top_k recent frames (time-range filter if given)."""
        if time_start is not None and time_end is not None:
            pairs = get_frames_in_range(thread_id, time_start, time_end)
            frames = [b64 for _, b64 in pairs]
        else:
            frames = get_frames_last_n_seconds(thread_id, seconds=_WINDOW_SECONDS)

        if not frames:
            return []
        sampled = _even_sample(frames, top_k)
        now = time.time()
        return [StoredFrame(timestamp=now, thread_id=thread_id, b64_jpeg=f) for f in sampled]

    def get_in_range(self, thread_id: str, start: float, end: float) -> list[StoredFrame]:
        pairs = get_frames_in_range(thread_id, start, end)
        return [StoredFrame(timestamp=ts, thread_id=thread_id, b64_jpeg=b64) for ts, b64 in pairs]

    def get_latest(self, thread_id: str, count: int = 1) -> list[StoredFrame]:
        frames = get_frames_last_n_seconds(thread_id, seconds=_WINDOW_SECONDS)
        recent = frames[-count:] if frames else []
        now = time.time()
        return [StoredFrame(timestamp=now, thread_id=thread_id, b64_jpeg=f) for f in recent]

    def count(self, thread_id: str) -> int:
        return len(get_frames_last_n_seconds(thread_id, seconds=_WINDOW_SECONDS))

    def clip_available(self) -> bool:
        return False


def _even_sample(frames: list[str], count: int) -> list[str]:
    if len(frames) <= count:
        return frames
    step = len(frames) / count
    return [frames[int(i * step)] for i in range(count)]


_frame_store = FrameStore()


def get_frame_store() -> FrameStore:
    return _frame_store
