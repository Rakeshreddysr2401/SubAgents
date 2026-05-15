"""Perception loop — motion-gated, event-driven VLM captioning via llama.cpp.

Called by the WebSocket handler on every incoming frame.
Runs motion detection synchronously (~1ms on CPU).
When motion is detected AND the cooldown has elapsed, fires a Gemma vision caption
in a background thread → result is written to EventLog.

Frames are already stored by webapp.py → frame_buffer. No double-storage here.

llama.cpp constraint: only ONE caption runs at a time (semaphore). This prevents
the thread pool from filling with queued requests while the model is busy.
The cooldown (90s) is intentionally long — multimodal inference takes 20-60s on a
laptop, so firing it more often just causes timeouts and blocks the chat model.

Separate machine tip: if you have a second machine with a GPU, set
VISION_BASE_URL=http://192.168.1.22:8080/v1 in your .env to route caption
traffic away from the supervisor chat model.
"""

import base64
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests

from src.configs.logging_config import get_logger
from src.llm_config import VISION_BASE_URL, VISION_MODEL_NAME, DISABLE_VISION
from src.utils.event_log import get_event_log

logger = get_logger(__name__)

# Allow routing vision to a separate llama.cpp instance.
_VISION_URL = os.getenv("VISION_BASE_URL", VISION_BASE_URL)

_MOTION_THRESHOLD = 2.5

# How long to wait after a caption before trying the next one.
# Gemma multimodal takes 20-60s on a laptop — 90s keeps the server free for chat.
_CAPTION_COOLDOWN = 90.0

_CAPTION_PROMPT = (
    "Describe this scene in 2-3 sentences. Cover: "
    "(1) what people are doing and their appearance (clothing colors, position), "
    "(2) notable objects visible and where they are, "
    "(3) the setting or environment. "
    "Be specific and factual. No speculation."
)

# Global semaphore: only 1 vision caption in flight at a time.
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
        """Dispatch a vision caption only if cooldown elapsed AND the model is free."""
        if DISABLE_VISION:
            return

        import time
        now = time.time()

        with self._lock:
            if now - self._last_caption.get(thread_id, 0.0) < _CAPTION_COOLDOWN:
                return

        if not _caption_semaphore.acquire(blocking=False):
            logger.debug("Vision model busy — skipping caption for thread=%s", thread_id)
            return

        with self._lock:
            self._last_caption[thread_id] = now

        _executor.submit(_caption_frame_async, thread_id, b64_jpeg)

    def reset_thread(self, thread_id: str):
        with self._lock:
            self._prev_frames.pop(thread_id, None)
            self._last_caption.pop(thread_id, None)


def _caption_frame_async(thread_id: str, b64_jpeg: str):
    """Send frame to Gemma vision via llama.cpp, write caption to EventLog."""
    try:
        resp = requests.post(
            f"{_VISION_URL}/chat/completions",
            headers={"Authorization": "Bearer not-needed", "Content-Type": "application/json"},
            json={
                "model": VISION_MODEL_NAME,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _CAPTION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64_jpeg}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 200,
                "stream": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        caption = resp.json()["choices"][0]["message"]["content"].strip()
        if caption:
            get_event_log().log(thread_id, caption, tags=["motion", "vlm"])
            logger.info("Caption: thread=%s — %s", thread_id, caption[:100])
    except requests.ConnectionError:
        logger.warning("Vision model not reachable at %s", _VISION_URL)
    except requests.Timeout:
        logger.warning("Vision model timed out (60s) for thread=%s", thread_id)
    except Exception as e:
        logger.exception("Caption failed for thread=%s: %s", thread_id, e)
    finally:
        _caption_semaphore.release()


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
