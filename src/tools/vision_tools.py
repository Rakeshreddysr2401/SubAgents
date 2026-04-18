"""Vision tools — real-time camera frame analysis via moondream.

look_now uses a tiered strategy to balance speed and quality:

  Tier 1 — Text metadata (instant, no VLM)
    For presence/detection queries ("is there a person?", "are there objects?"),
    answers directly from YOLO tags and BLIP captions — no Ollama call.

  Tier 2 — Relevance search + VLM (2-5s with moondream)
    Finds the most relevant frame from the last 5 minutes via YOLO tag scoring.
    Enriches the VLM prompt with YOLO/BLIP context for a better answer.
    Uses moondream (1.6B) by default — fast enough for laptops and Jetson.

  Tier 3 — Fallback (latest raw frame)
    If frame_store has no YOLO-tagged frames, sends the latest raw frame.

The _caption_semaphore is shared with perception_loop so background moondream
captions and user look_now calls never hit Ollama simultaneously.
"""

import os
import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.utils.frame_buffer import get_latest_frames
from src.utils.frame_store import get_frame_store, StoredFrame
from src.llm_config import OLLAMA_BASE_URL
from src.configs.logging_config import get_logger
from src.utils.perception_loop import _caption_semaphore

logger = get_logger(__name__)

_VISION_MODEL = os.getenv("VISION_MODEL", "moondream")
_VISION_URL   = os.getenv("OLLAMA_VISION_URL", OLLAMA_BASE_URL)

# Phrases that indicate a presence/detection query YOLO alone can answer
_DETECTION_PHRASES = (
    "is there", "is someone", "is anyone", "are there", "was there",
    "anyone in", "anyone here", "person in", "people in",
    "do you see", "can you see",
)


def _is_detection_query(query: str) -> bool:
    q = query.lower()
    return any(phrase in q for phrase in _DETECTION_PHRASES)


def _metadata_answer(frames: list[StoredFrame]) -> str | None:
    """Build a text answer from YOLO tags + BLIP captions. Returns None if empty."""
    all_tags: list[str] = []
    blip_texts: list[str] = []
    for f in frames:
        for t in f.yolo_tags:
            if t not in all_tags:
                all_tags.append(t)
        if f.blip_caption:
            blip_texts.append(f.blip_caption)

    if not all_tags and not blip_texts:
        return None

    parts = []
    if all_tags:
        parts.append(f"Objects detected: {', '.join(all_tags)}")
    if blip_texts:
        parts.append(f"Scene: {blip_texts[-1]}")
    return "\n".join(parts)


def _build_context(frames: list[StoredFrame]) -> str:
    """Build a short metadata context string to prepend to the VLM query."""
    all_tags: list[str] = []
    blip_texts: list[str] = []
    for f in frames:
        for t in f.yolo_tags:
            if t not in all_tags:
                all_tags.append(t)
        if f.blip_caption:
            blip_texts.append(f.blip_caption)

    parts = []
    if all_tags:
        parts.append(f"Objects detected: {', '.join(all_tags[:12])}")
    if blip_texts:
        parts.append(f"Scene context: {blip_texts[-1]}")
    return "\n".join(parts)


@tool
def look_now(query: str, config: RunnableConfig) -> str:
    """Take a fresh camera frame right now and answer a specific visual question.

    Searches the last 5 minutes of frames for the most relevant one to your
    question. First tries to answer from text metadata (YOLO detections, scene
    descriptions) — falls back to the vision model only when visual detail is
    truly needed.

    Use this when recall_world and recall_recent cannot answer:
    - "what color is my shirt / bag / item?"
    - "how many people are in the room?"
    - "what am I doing right now?"
    - "what is on the desk?"
    - "describe the current scene in detail"
    - "is there a [specific object] visible?"
    - any question requiring fine visual detail

    Args:
        query: Your specific question about what the camera currently sees.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    store     = get_frame_store()
    relevant  = store.search(thread_id, query, top_k=3)

    if relevant:
        unique_tags: list[str] = []
        for f in relevant:
            for t in f.yolo_tags:
                if t not in unique_tags:
                    unique_tags.append(t)
        logger.info(
            "look_now: %d frame(s) via YOLO search. Tags: %s — query=%s",
            len(relevant), unique_tags[:8], query[:60],
        )

        # Tier 1: Answer detection queries from YOLO metadata (no VLM call)
        if _is_detection_query(query):
            meta = _metadata_answer(relevant)
            if meta:
                logger.info("look_now: detection query answered from YOLO metadata (no VLM)")
                return meta

        frames_to_send = [f.b64_jpeg for f in relevant]
        ctx = _build_context(relevant)
        enriched_query = f"{ctx}\n\n{query}".strip() if ctx else query

    else:
        # Tier 3: Fallback to latest raw frame
        raw = get_latest_frames(thread_id, count=1)
        if not raw:
            return (
                "No camera frames available. "
                "Make sure the camera is enabled and streaming."
            )
        frames_to_send = raw
        enriched_query = query
        logger.info(
            "look_now: no YOLO-tagged frames — using latest raw frame. query=%s",
            query[:60],
        )

    # Tier 2 / Tier 3 VLM call
    logger.info("look_now: waiting for %s slot...", _VISION_MODEL)
    _caption_semaphore.acquire()
    try:
        resp = requests.post(
            f"{_VISION_URL}/api/generate",
            json={
                "model":  _VISION_MODEL,
                "prompt": enriched_query,
                "images": frames_to_send[:2],  # 1-2 frames; moondream handles both
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        if not answer:
            return "Vision model returned no response."
        return answer

    except requests.ConnectionError:
        return (
            f"Vision service (Ollama/{_VISION_MODEL}) is not reachable at {_VISION_URL}. "
            "Make sure Ollama is running: ollama serve"
        )
    except requests.Timeout:
        return (
            f"Vision model timed out (120s). {_VISION_MODEL} may still be loading. "
            "Try again in a moment."
        )
    except Exception as e:
        logger.exception("look_now error: %s", e)
        return f"Visual analysis failed: {e}"
    finally:
        _caption_semaphore.release()
