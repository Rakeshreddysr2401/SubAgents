"""Perception loop — motion-gated, event-driven VLM captioning.

Called by the WebSocket handler on every incoming frame.
Runs motion detection synchronously (cheap, ~1ms).
When motion is detected AND the cooldown has elapsed, fires a VLM caption
in a background thread → result is written to EventLog.

Frames are already stored by webapp.py → frame_buffer. No double-storage here.

Motion detection uses OpenCV frame differencing (absdiff on grayscale).
No model required — runs on CPU in under 1ms per frame.
"""

import base64
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

from src.configs.logging_config import get_logger
from src.llm_config import OLLAMA_BASE_URL
from src.utils.event_log import get_event_log

logger = get_logger(__name__)

_MOTION_THRESHOLD = 2.5   # mean pixel diff to trigger caption
_CAPTION_COOLDOWN = 8.0   # seconds between VLM calls per thread (raised to ease laptop load)
_CAPTION_PROMPT = (
    "Describe this scene in 2-3 sentences. Cover: "
    "(1) what people are doing and their appearance (clothing colors, position), "
    "(2) notable objects visible and where they are, "
    "(3) the setting or environment. "
    "Be specific and factual. No speculation."
)

# 2 workers is enough: one active caption at a time + one queued
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="perception")


class PerceptionLoop:
    """Stateful per-thread motion detector and VLM trigger."""

    def __init__(self):
        self._lock = threading.Lock()
        self._prev_frames: dict[str, np.ndarray] = {}
        self._last_caption: dict[str, float] = {}

    def on_frame(self, thread_id: str, b64_jpeg: str) -> bool:
        """Process an incoming frame. Returns True if motion was detected."""
        gray = _decode_to_gray(b64_jpeg)
        if gray is None:
            return False

        motion = self._detect_motion(thread_id, gray)

        if motion:
            self._maybe_caption(thread_id, b64_jpeg)

        return motion

    def _detect_motion(self, thread_id: str, gray: np.ndarray) -> bool:
        with self._lock:
            prev = self._prev_frames.get(thread_id)
            self._prev_frames[thread_id] = gray

        if prev is None or prev.shape != gray.shape:
            return False

        diff = np.abs(gray.astype(np.int16) - prev.astype(np.int16))
        score = float(diff.mean())
        motion = score > _MOTION_THRESHOLD

        if motion:
            logger.debug("Motion: thread=%s score=%.2f", thread_id, score)

        return motion

    def _maybe_caption(self, thread_id: str, b64_jpeg: str):
        """Submit a VLM caption task if cooldown has elapsed."""
        import time
        now = time.time()
        with self._lock:
            last = self._last_caption.get(thread_id, 0.0)
            if now - last < _CAPTION_COOLDOWN:
                return
            self._last_caption[thread_id] = now

        _executor.submit(_caption_frame_async, thread_id, b64_jpeg)

    def reset_thread(self, thread_id: str):
        with self._lock:
            self._prev_frames.pop(thread_id, None)
            self._last_caption.pop(thread_id, None)


def _caption_frame_async(thread_id: str, b64_jpeg: str):
    """Send frame to LLaVA, write caption to EventLog."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": "llava",
                "prompt": _CAPTION_PROMPT,
                "images": [b64_jpeg],
                "stream": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        caption = resp.json().get("response", "").strip()
        if caption:
            get_event_log().log(thread_id, caption, tags=["motion", "vlm"])
            logger.debug("Caption: thread=%s — %s", thread_id, caption[:80])
    except requests.ConnectionError:
        logger.warning("LLaVA not reachable at %s", OLLAMA_BASE_URL)
    except requests.Timeout:
        logger.warning("LLaVA timed out for thread=%s", thread_id)
    except Exception as e:
        logger.exception("Caption failed for thread=%s: %s", thread_id, e)


def _decode_to_gray(b64_jpeg: str) -> np.ndarray | None:
    """Decode base64 JPEG to a small grayscale numpy array. Returns None on failure."""
    try:
        import cv2
        data = base64.b64decode(b64_jpeg)
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if frame is None:
            return None
        # 160x120 is plenty for motion detection — half the previous size
        return cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.warning("Frame decode failed: %s", e)
        return None


_loop = PerceptionLoop()


def get_perception_loop() -> PerceptionLoop:
    return _loop
