"""Perception loop — motion-gated scene understanding.

Three independent paths triggered on motion:

  PATH A — YOLO (15s cooldown, CPU, ~100ms)
    Detects which objects are present → stored in frame_store for smart frame search.
    No Ollama, no semaphore.

  PATH B — moondream (20s cooldown, Ollama, 2-5s)
    Produces a structured observation covering people, objects, activity, environment.
    Output splits into:
      → event_log  (timestamped text, used by recall_recent)
      → world_model (current-state JSON, used by recall_world)
    Uses the _caption_semaphore shared with look_now so Ollama is never double-called.

  PATH C — (future) audio, depth, etc.

Why moondream instead of LLaVA:
  - 1.6B params vs 7B  →  2-5s vs 30-60s per frame
  - Can caption every 20s instead of 90s  →  denser, richer memory
  - Same Ollama API  →  zero code changes to integration
  - Frees Ollama for the chat model between captions

Install: ollama pull moondream
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
from src.utils.frame_store import get_frame_store
from src.core.world_model import get_world_model
from src.utils import yolo_detector, blip_captioner

logger = get_logger(__name__)

_VISION_URL    = os.getenv("OLLAMA_VISION_URL", OLLAMA_BASE_URL)
_CAPTION_MODEL = os.getenv("VISION_MODEL", "moondream")   # override with VISION_MODEL=llava if needed

_MOTION_THRESHOLD = 2.5
_YOLO_COOLDOWN    = 15.0   # YOLO: fast, frequent frame indexing
_CAPTION_COOLDOWN = 20.0   # moondream: 2-5s so 20s cooldown is safe

# Shared with vision_tools.look_now — only 1 Ollama vision call at a time
_caption_semaphore = threading.Semaphore(1)

_caption_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moondream")
_fast_executor    = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yolo")

# ---------------------------------------------------------------------------
# Structured prompt — one call extracts everything needed for both stores
# ---------------------------------------------------------------------------
_CAPTION_PROMPT = """\
Look at this image carefully and respond in EXACTLY this format (one line each):

CAPTION: [2-3 sentences: describe the full scene, people, objects, what's happening]
PEOPLE: [who is present, clothing colors, what they are doing — or write: none]
OBJECTS: [list visible objects and their locations — or write: none]
ACTIVITY: [the main activity in one short sentence]
ENVIRONMENT: [room type and lighting condition]

Keep each line factual and concise. Do not add extra lines or commentary.\
"""


class PerceptionLoop:
    """Stateful per-thread motion detector that triggers YOLO and moondream."""

    def __init__(self):
        self._lock         = threading.Lock()
        self._prev_frames:  dict[str, np.ndarray] = {}
        self._last_caption: dict[str, float]       = {}
        self._last_yolo:    dict[str, float]        = {}

    def on_frame(self, thread_id: str, b64_jpeg: str) -> bool:
        """Process one camera frame. Returns True if motion detected.
        Must return quickly — heavy work is dispatched to executors.
        """
        gray = _decode_to_gray(b64_jpeg)
        if gray is None:
            return False

        if not self._detect_motion(thread_id, gray):
            return False

        self._maybe_yolo_store(thread_id, b64_jpeg)   # Path A — fast
        self._maybe_caption(thread_id, b64_jpeg)       # Path B — moondream
        return True

    # ------------------------------------------------------------------
    # Motion detection
    # ------------------------------------------------------------------

    def _detect_motion(self, thread_id: str, gray: np.ndarray) -> bool:
        with self._lock:
            prev = self._prev_frames.get(thread_id)
            self._prev_frames[thread_id] = gray

        if prev is None or prev.shape != gray.shape:
            return False

        diff   = np.abs(gray.astype(np.int16) - prev.astype(np.int16))
        motion = float(diff.mean()) > _MOTION_THRESHOLD
        if motion:
            logger.debug("Motion: thread=%s", thread_id)
        return motion

    # ------------------------------------------------------------------
    # Path A — YOLO
    # ------------------------------------------------------------------

    def _maybe_yolo_store(self, thread_id: str, b64_jpeg: str):
        import time
        now = time.time()
        with self._lock:
            if now - self._last_yolo.get(thread_id, 0.0) < _YOLO_COOLDOWN:
                return
            self._last_yolo[thread_id] = now
        _fast_executor.submit(_yolo_store_async, thread_id, b64_jpeg)

    # ------------------------------------------------------------------
    # Path B — moondream caption + world model
    # ------------------------------------------------------------------

    def _maybe_caption(self, thread_id: str, b64_jpeg: str):
        import time
        now = time.time()
        with self._lock:
            if now - self._last_caption.get(thread_id, 0.0) < _CAPTION_COOLDOWN:
                return

        if not _caption_semaphore.acquire(blocking=False):
            logger.debug("moondream busy — skipping caption for thread=%s", thread_id)
            return

        with self._lock:
            self._last_caption[thread_id] = now

        _caption_executor.submit(_caption_frame_async, thread_id, b64_jpeg)

    # ------------------------------------------------------------------

    def reset_thread(self, thread_id: str):
        with self._lock:
            self._prev_frames.pop(thread_id, None)
            self._last_caption.pop(thread_id, None)
            self._last_yolo.pop(thread_id, None)


# ---------------------------------------------------------------------------
# Async workers
# ---------------------------------------------------------------------------

def _yolo_store_async(thread_id: str, b64_jpeg: str):
    """YOLO detection → frame_store with tags. CPU-only, no semaphore."""
    try:
        tags = yolo_detector.detect_objects(b64_jpeg)
        cap  = blip_captioner.caption(b64_jpeg)
        get_frame_store().store(thread_id=thread_id, b64_jpeg=b64_jpeg,
                                yolo_tags=tags, blip_caption=cap)
        if tags:
            logger.info("YOLO[%s]: %s", thread_id, tags)
    except Exception as e:
        logger.exception("_yolo_store_async failed: %s", e)


def _caption_frame_async(thread_id: str, b64_jpeg: str):
    """moondream structured observation → event_log + world_model.
    Releases semaphore in finally — always, even on timeout or error.
    """
    try:
        resp = requests.post(
            f"{_VISION_URL}/api/generate",
            json={
                "model":  _CAPTION_MODEL,
                "prompt": _CAPTION_PROMPT,
                "images": [b64_jpeg],
                "stream": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        if not raw:
            return

        parsed = _parse_structured_response(raw)

        # Write caption to event_log (powers recall_recent)
        caption = parsed.get("caption") or raw
        get_event_log().log(thread_id, caption, tags=["motion", "moondream"])
        logger.info("Caption[%s]: %s", thread_id, caption[:100])

        # Update world model (powers recall_world)
        get_world_model().update(
            people      = parsed.get("people", ""),
            objects     = parsed.get("objects", ""),
            activity    = parsed.get("activity", ""),
            environment = parsed.get("environment", ""),
            caption     = caption,
        )

    except requests.ConnectionError:
        logger.warning("moondream not reachable at %s — is Ollama running?", _VISION_URL)
    except requests.Timeout:
        logger.warning("moondream timed out (60s) for thread=%s", thread_id)
    except Exception as e:
        logger.exception("Caption failed for thread=%s: %s", thread_id, e)
    finally:
        _caption_semaphore.release()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_structured_response(text: str) -> dict:
    """Parse the structured moondream response into named fields.

    Expected format:
      CAPTION: ...
      PEOPLE: ...
      OBJECTS: ...
      ACTIVITY: ...
      ENVIRONMENT: ...

    Handles moondream not following the format perfectly — falls back to
    storing the full response as the caption.
    """
    result: dict[str, str] = {}
    keys = ("CAPTION", "PEOPLE", "OBJECTS", "ACTIVITY", "ENVIRONMENT")

    for line in text.split("\n"):
        line = line.strip()
        for key in keys:
            prefix = f"{key}:"
            if line.upper().startswith(prefix):
                value = line[len(prefix):].strip()
                if value:
                    result[key.lower()] = value
                break

    if not result:
        # moondream didn't follow the format — store full text as caption
        result["caption"] = text

    return result


def _decode_to_gray(b64_jpeg: str) -> np.ndarray | None:
    """Decode base64 JPEG → 160×120 grayscale array for motion diff."""
    try:
        import cv2
        data  = base64.b64decode(b64_jpeg)
        arr   = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if frame is None:
            return None
        return cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.warning("Frame decode failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_loop = PerceptionLoop()


def get_perception_loop() -> PerceptionLoop:
    return _loop
