"""Perception loop — motion-gated, event-driven VLM captioning.

Called by the WebSocket handler on every incoming frame.
Runs motion detection synchronously (cheap, ~1ms on CPU).
When motion is detected AND the cooldown has elapsed, fires a VLM caption
in a background thread → result is written to EventLog.

Frames are already stored by webapp.py → frame_buffer. No double-storage here.

LLaVA constraint: only ONE caption runs at a time (semaphore). This prevents
the thread pool from filling with queued requests while Ollama is busy.
The cooldown (90s) is intentionally long — LLaVA takes 30-60s on a laptop,
so firing it more often than that just causes timeouts and blocks the chat model.

Mac Mini tip: if you have LLaVA on your Mac Mini (192.168.1.22:11434), set
OLLAMA_VISION_URL=http://192.168.1.22:11434 in your .env to separate caption
traffic from the supervisor chat model (which stays on localhost:11434).
"""

import base64
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

from src.configs.logging_config import get_logger
from src.llm_config import OLLAMA_BASE_URL
from src.utils.event_log import get_event_log

logger = get_logger(__name__)

# Optionally route LLaVA to a separate machine (e.g. Mac Mini) so it doesn't
# block the supervisor's chat model on localhost Ollama.
_VISION_URL = os.getenv("OLLAMA_VISION_URL", OLLAMA_BASE_URL)

_MOTION_THRESHOLD = 2.5

# How long to wait after a caption before trying the next one.
# LLaVA takes 30-60s on a laptop — 90s gives it room to finish and keeps
# Ollama free for the supervisor chat model in between.
_CAPTION_COOLDOWN = 90.0

_CAPTION_PROMPT = (
    "Describe this scene in 2-3 sentences. Cover: "
    "(1) what people are doing and their appearance (clothing colors, position), "
    "(2) notable objects visible and where they are, "
    "(3) the setting or environment. "
    "Be specific and factual. No speculation."
)

# Global semaphore: only 1 LLaVA caption in flight at a time.
# Without this, a 30s LLaVA call + 8s cooldown = thread pool always full.
_caption_semaphore = threading.Semaphore(1)

# 1 worker is enough — captions are serialised by the semaphore anyway.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="perception")


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
        motion = float(diff.mean()) > _MOTION_THRESHOLD

        if motion:
            logger.debug("Motion: thread=%s", thread_id)

        return motion

    def _maybe_caption(self, thread_id: str, b64_jpeg: str):
        """Dispatch a VLM caption only if cooldown elapsed AND Ollama is free."""
        import time
        now = time.time()

        # Check per-thread cooldown
        with self._lock:
            if now - self._last_caption.get(thread_id, 0.0) < _CAPTION_COOLDOWN:
                return

        # Check global LLaVA slot (non-blocking)
        if not _caption_semaphore.acquire(blocking=False):
            logger.debug("LLaVA busy — skipping caption for thread=%s", thread_id)
            return

        # Got the slot — lock in the timestamp and fire
        with self._lock:
            self._last_caption[thread_id] = now

        _executor.submit(_caption_frame_async, thread_id, b64_jpeg)

    def reset_thread(self, thread_id: str):
        with self._lock:
            self._prev_frames.pop(thread_id, None)
            self._last_caption.pop(thread_id, None)


def _caption_frame_async(thread_id: str, b64_jpeg: str):
    """Send frame to LLaVA, write caption to EventLog. Releases semaphore when done."""
    try:
        resp = requests.post(
            f"{_VISION_URL}/api/generate",
            json={
                "model": "llava",
                "prompt": _CAPTION_PROMPT,
                "images": [b64_jpeg],
                "stream": False,
            },
            timeout=60,  # LLaVA can take 45s on first call (model loading)
        )
        resp.raise_for_status()
        caption = resp.json().get("response", "").strip()
        if caption:
            get_event_log().log(thread_id, caption, tags=["motion", "vlm"])
            logger.info("Caption: thread=%s — %s", thread_id, caption[:100])
    except requests.ConnectionError:
        logger.warning("LLaVA not reachable at %s", _VISION_URL)
    except requests.Timeout:
        logger.warning("LLaVA timed out (60s) for thread=%s — Ollama may be overloaded", thread_id)
    except Exception as e:
        logger.exception("Caption failed for thread=%s: %s", thread_id, e)
    finally:
        _caption_semaphore.release()  # always release, even on timeout


def _decode_to_gray(b64_jpeg: str) -> np.ndarray | None:
    """Decode base64 JPEG to a small grayscale array. Returns None on failure."""
    try:
        import cv2
        data = base64.b64decode(b64_jpeg)
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if frame is None:
            return None
        return cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.warning("Frame decode failed: %s", e)
        return None


_loop = PerceptionLoop()


def get_perception_loop() -> PerceptionLoop:
    return _loop
