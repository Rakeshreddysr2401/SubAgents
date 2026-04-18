"""Frame store — motion-triggered frames with YOLO tags and optional BLIP captions.

Stores frames that were captured on motion events (not every browser frame).
Each StoredFrame carries:
  - yolo_tags:    objects detected by YOLOv8n  e.g. ["person", "laptop", "cup"]
  - blip_caption: one-sentence BLIP description e.g. "a man sitting at a desk"

The search() method finds the most relevant frames for a natural-language query
by scoring YOLO tags and BLIP captions against extracted keywords. This allows
look_now to send the right historical frame to LLaVA instead of always the latest.

Frame fallback: if frame_store is empty or no frame matches the query,
look_now falls back to frame_buffer (raw, always-available latest frame).

Thread-safe: threading.Lock() guards all read/write operations.
Rolling window: 5 minutes — frames older than 300s are evicted on each store().
"""

import threading
import time
from dataclasses import dataclass, field

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

_WINDOW_SECONDS = 300   # 5-minute rolling window

# ---------------------------------------------------------------------------
# Keyword extraction helpers
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "how", "many", "much", "does", "do", "did", "have", "has", "had",
    "what", "where", "when", "who", "which", "that", "this", "these", "those",
    "there", "their", "they", "he", "she", "it", "i", "you", "we",
    "of", "in", "on", "at", "to", "and", "or", "but", "with", "for",
    "from", "by", "as", "can", "could", "would", "should", "will", "shall",
    "his", "her", "its", "my", "your", "our",
    "right", "now", "currently", "please", "tell", "me", "show", "see",
    "any", "some", "all", "more", "most", "just", "only", "also",
    "get", "look", "find", "about", "up", "out", "so", "not", "no",
    "here", "look", "like", "going", "let",
})

# Map natural-language words → YOLO COCO class names
_SYNONYMS: dict[str, str] = {
    "man":        "person",
    "woman":      "person",
    "guy":        "person",
    "girl":       "person",
    "boy":        "person",
    "lady":       "person",
    "men":        "person",
    "women":      "person",
    "people":     "person",
    "human":      "person",
    "someone":    "person",
    "somebody":   "person",
    "person":     "person",
    "phone":      "cell phone",
    "smartphone": "cell phone",
    "mobile":     "cell phone",
    "computer":   "laptop",
    "pc":         "laptop",
    "monitor":    "tv",
    "television": "tv",
    "screen":     "tv",
    "glass":      "wine glass",
    "glasses":    "wine glass",
    "mug":        "cup",
    "sofa":       "couch",
    "bike":       "bicycle",
    "dog":        "dog",
    "cat":        "cat",
    "car":        "car",
    "table":      "dining table",
    "desk":       "dining table",
    "chair":      "chair",
    "bottle":     "bottle",
    "bowl":       "bowl",
    "book":       "book",
    "clock":      "clock",
    "bag":        "handbag",
    "backpack":   "backpack",
}


def _extract_keywords(query: str) -> list[str]:
    """Extract meaningful search keywords from a natural-language query.

    Lowercases, strips punctuation, removes stopwords, and applies
    synonym mapping (e.g. "man" → "person") so keywords align with YOLO classes.
    """
    words = (
        query.lower()
        .replace("?", "")
        .replace("!", "")
        .replace(",", "")
        .replace(".", "")
        .split()
    )
    keywords: list[str] = []
    for w in words:
        if w in _STOPWORDS:
            continue
        mapped = _SYNONYMS.get(w, w)
        if mapped not in keywords:
            keywords.append(mapped)
    return keywords


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class StoredFrame:
    timestamp:    float
    thread_id:    str
    b64_jpeg:     str
    yolo_tags:    list[str] = field(default_factory=list)
    blip_caption: str = ""


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class FrameStore:
    """Thread-safe store of motion-triggered frames with YOLO/BLIP metadata."""

    def __init__(self):
        self._lock = threading.Lock()
        # thread_id -> list[StoredFrame], sorted by timestamp (oldest first)
        self._frames: dict[str, list[StoredFrame]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(
        self,
        thread_id: str,
        b64_jpeg: str,
        yolo_tags: list[str] | None = None,
        blip_caption: str = "",
        timestamp: float | None = None,
    ) -> StoredFrame:
        """Store a motion-triggered frame with its metadata.

        Evicts frames older than 5 minutes on each call.

        Args:
            thread_id:    Browser session / conversation thread.
            b64_jpeg:     Base64-encoded JPEG string.
            yolo_tags:    Detected object class names from YOLO.
            blip_caption: Optional BLIP base description.
            timestamp:    Unix timestamp (defaults to now).
        """
        ts = timestamp or time.time()
        cutoff = ts - _WINDOW_SECONDS

        frame = StoredFrame(
            timestamp=ts,
            thread_id=thread_id,
            b64_jpeg=b64_jpeg,
            yolo_tags=yolo_tags or [],
            blip_caption=blip_caption,
        )

        with self._lock:
            frames = self._frames.setdefault(thread_id, [])
            frames.append(frame)
            # Evict old frames (left-side, oldest first)
            self._frames[thread_id] = [f for f in frames if f.timestamp >= cutoff]

        logger.debug(
            "FrameStore[%s]: stored ts=%.0f yolo=%s blip=%s",
            thread_id, ts, yolo_tags or [], bool(blip_caption),
        )
        return frame

    # ------------------------------------------------------------------
    # Search — keyword-based relevance scoring
    # ------------------------------------------------------------------

    def search(
        self,
        thread_id: str,
        query: str,
        top_k: int = 2,
    ) -> list[StoredFrame]:
        """Find the most relevant frames for a query.

        Scoring (higher = more relevant):
          +3.0  exact YOLO tag match with a keyword
          +1.5  partial YOLO tag match (substring either direction)
          +0.5  keyword found in BLIP caption text
          +0-0.2 recency bonus (tie-break only)

        Falls back to the most recent `top_k` frames if no frame scores > 0.
        Returns [] only if there are no stored frames at all.

        Args:
            thread_id: Browser session thread.
            query:     The user's natural-language question.
            top_k:     Maximum frames to return.
        """
        with self._lock:
            frames = list(self._frames.get(thread_id, []))

        if not frames:
            return []

        keywords = _extract_keywords(query)
        logger.debug("frame_store.search: keywords=%s", keywords)

        if not keywords:
            # Nothing meaningful to match — return most recent
            return frames[-top_k:]

        now = time.time()
        scored: list[tuple[StoredFrame, float]] = []

        for frame in frames:
            score = 0.0

            for kw in keywords:
                for tag in frame.yolo_tags:
                    if kw == tag:
                        score += 3.0          # exact match
                    elif kw in tag or tag in kw:
                        score += 1.5          # partial match

            if frame.blip_caption:
                blip_lower = frame.blip_caption.lower()
                for kw in keywords:
                    if kw in blip_lower:
                        score += 0.5

            # Recency bonus: 0.0 (oldest) → 0.2 (newest) — tie-break only
            age_fraction = max(0.0, (now - frame.timestamp) / _WINDOW_SECONDS)
            score += (1.0 - age_fraction) * 0.2

            scored.append((frame, score))

        # Filter to frames with at least one meaningful signal (score > 0.2 = beyond recency only)
        matched = [(f, s) for f, s in scored if s > 0.2]

        if not matched:
            logger.debug("frame_store.search: no keyword match — returning latest %d frames", top_k)
            return frames[-top_k:]

        matched.sort(key=lambda x: x[1], reverse=True)
        result = [f for f, _ in matched[:top_k]]
        logger.info(
            "frame_store.search: returning %d frames (scores %s) for query=%s",
            len(result),
            [round(s, 1) for _, s in matched[:top_k]],
            query[:60],
        )
        return result

    # ------------------------------------------------------------------
    # Read — direct access
    # ------------------------------------------------------------------

    def get_latest(self, thread_id: str, count: int = 1) -> list[StoredFrame]:
        """Return the most recent `count` stored frames."""
        with self._lock:
            frames = self._frames.get(thread_id, [])
            return frames[-count:] if frames else []

    def get_in_range(self, thread_id: str, start: float, end: float) -> list[StoredFrame]:
        """Return all frames whose timestamp falls within [start, end]."""
        with self._lock:
            frames = self._frames.get(thread_id, [])
            return [f for f in frames if start <= f.timestamp <= end]

    def count(self, thread_id: str) -> int:
        """Return number of frames currently stored for a thread."""
        with self._lock:
            return len(self._frames.get(thread_id, []))

    def clip_available(self) -> bool:
        """Always False — CLIP is disabled."""
        return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_frame_store = FrameStore()


def get_frame_store() -> FrameStore:
    return _frame_store
