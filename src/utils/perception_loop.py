"""Perception loop — motion-gated, event-driven frame processing.

Called by the WebSocket handler on every incoming frame.
Runs motion detection synchronously (cheap, ~1ms).
When motion is detected, fires async threads for:
  1. FrameStore.store()   — compress + CLIP embed + save
  2. VLM caption          — LLaVA describes the scene → EventLog

This means the WebSocket handler is never blocked by VLM inference.

Motion detection uses OpenCV frame differencing (absdiff on grayscale).
No model required — runs on CPU in under 1ms per frame.

Architecture:
  WebSocket → on_frame(thread_id, b64) → [motion gate]
                                               │
                              ┌────────────────┘
                              │ motion detected
                              ▼
                    [FrameStore.store()]  ← async thread
                    [VLM caption]         ← async thread → EventLog
"""

import base64
import io
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

from src.configs.logging_config import get_logger
from src.llm_config import OLLAMA_BASE_URL
from src.utils.event_log import get_event_log
from src.utils.frame_store import get_frame_store

logger = get_logger(__name__)

# Motion detection threshold — mean pixel difference to trigger processing.
# Lower = more sensitive. Tune based on lighting / camera stability.
_MOTION_THRESHOLD = 2.5

# Minimum seconds between VLM captions for the same thread.
# Prevents flooding LLaVA when there's continuous motion.
_CAPTION_COOLDOWN = 5.0

# VLM prompt — brief, factual, present-tense description
_CAPTION_PROMPT = (
    "Describe what is happening in this image in one concise sentence. "
    "Focus on people, objects, and actions. Be factual and brief."
)

# Thread pool for async VLM + store operations (daemon so app exits cleanly)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="perception")


class PerceptionLoop:
    """Stateful per-thread motion detector and VLM trigger."""

    def __init__(self):
        self._lock = threading.Lock()
        # thread_id -> previous grayscale frame as numpy uint8 array
        self._prev_frames: dict[str, np.ndarray] = {}
        # thread_id -> timestamp of last VLM caption
        self._last_caption: dict[str, float] = {}

    def on_frame(self, thread_id: str, b64_jpeg: str) -> bool:
        """Process an incoming frame. Returns True if motion was detected.

        Called synchronously from the WebSocket handler — must be fast.
        Heavy work (FrameStore, VLM) is dispatched to the thread pool.
        """
        gray = _decode_to_gray(b64_jpeg)
        if gray is None:
            return False

        motion = self._detect_motion(thread_id, gray)

        if motion:
            self._handle_motion(thread_id, b64_jpeg)

        return motion

    # ------------------------------------------------------------------
    # Motion detection
    # ------------------------------------------------------------------

    def _detect_motion(self, thread_id: str, gray: np.ndarray) -> bool:
        with self._lock:
            prev = self._prev_frames.get(thread_id)
            self._prev_frames[thread_id] = gray

        if prev is None:
            return False  # first frame — no comparison possible

        if prev.shape != gray.shape:
            return False  # resolution changed

        diff = np.abs(gray.astype(np.int16) - prev.astype(np.int16))
        score = float(diff.mean())
        motion = score > _MOTION_THRESHOLD

        if motion:
            logger.debug("Motion detected: thread=%s score=%.2f", thread_id, score)

        return motion

    # ------------------------------------------------------------------
    # Motion handling
    # ------------------------------------------------------------------

    def _handle_motion(self, thread_id: str, b64_jpeg: str):
        """Dispatch async tasks for frame storage and captioning."""
        # Always store the frame (non-blocking)
        _executor.submit(_store_frame_async, thread_id, b64_jpeg)

        # Caption with VLM, respecting cooldown
        import time
        now = time.time()
        with self._lock:
            last = self._last_caption.get(thread_id, 0.0)
            if now - last >= _CAPTION_COOLDOWN:
                self._last_caption[thread_id] = now
                should_caption = True
            else:
                should_caption = False

        if should_caption:
            _executor.submit(_caption_frame_async, thread_id, b64_jpeg)

    def set_motion_threshold(self, value: float):
        """Adjust motion sensitivity at runtime."""
        global _MOTION_THRESHOLD
        _MOTION_THRESHOLD = value
        logger.info("Motion threshold set to %.2f", value)

    def set_caption_cooldown(self, seconds: float):
        """Adjust minimum gap between VLM captions at runtime."""
        global _CAPTION_COOLDOWN
        _CAPTION_COOLDOWN = seconds
        logger.info("Caption cooldown set to %.1fs", seconds)

    def reset_thread(self, thread_id: str):
        """Clear state for a thread (e.g. on disconnect)."""
        with self._lock:
            self._prev_frames.pop(thread_id, None)
            self._last_caption.pop(thread_id, None)


# ---------------------------------------------------------------------------
# Async workers (run in thread pool, not on the event loop)
# ---------------------------------------------------------------------------

def _store_frame_async(thread_id: str, b64_jpeg: str):
    """Compress + CLIP-embed + store frame in FrameStore."""
    try:
        get_frame_store().store(thread_id, b64_jpeg)
    except Exception as e:
        logger.exception("FrameStore.store failed for thread=%s: %s", thread_id, e)


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
            logger.debug("Caption logged for thread=%s: %s", thread_id, caption[:80])
    except requests.ConnectionError:
        logger.warning("LLaVA not reachable at %s — caption skipped", OLLAMA_BASE_URL)
    except requests.Timeout:
        logger.warning("LLaVA timed out — caption skipped for thread=%s", thread_id)
    except Exception as e:
        logger.exception("Caption async failed for thread=%s: %s", thread_id, e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_to_gray(b64_jpeg: str) -> np.ndarray | None:
    """Decode base64 JPEG to a grayscale numpy array. Returns None on failure."""
    try:
        import cv2
        data = base64.b64decode(b64_jpeg)
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if frame is None:
            return None
        # Downscale for faster diff — 320x240 is sufficient for motion detection
        return cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.warning("Frame decode failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_loop = PerceptionLoop()


def get_perception_loop() -> PerceptionLoop:
    return _loop
