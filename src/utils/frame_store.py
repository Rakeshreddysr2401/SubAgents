"""Frame store — compressed frames with CLIP embeddings for semantic retrieval.

Stores every motion-triggered frame as:
  (timestamp, compressed_base64_jpeg, clip_embedding)

CLIP allows semantic search: "blue shirt with buttons" retrieves the most
visually relevant frames without scanning every frame with LLaVA.

CLIP is optional — if open_clip is not installed the store still works but
search falls back to time-range retrieval instead of semantic similarity.

Rolling window: 5 minutes (matches frame_buffer.py).
"""

import base64
import io
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

_WINDOW_SECONDS = 300  # 5-minute rolling window
_JPEG_QUALITY = 40     # Compress harder than the source for storage efficiency

# ---------------------------------------------------------------------------
# CLIP — lazy load so the app starts even if open_clip is not installed
# ---------------------------------------------------------------------------
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None
_clip_available = False


def _load_clip():
    global _clip_model, _clip_preprocess, _clip_tokenizer, _clip_available
    if _clip_available:
        return True
    try:
        import open_clip
        import torch
        _clip_model, _, _clip_preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="openai"
        )
        _clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
        _clip_model.eval()
        _clip_available = True
        logger.info("CLIP loaded (ViT-B/32)")
        return True
    except ImportError:
        logger.warning("open_clip not installed — semantic frame search disabled. "
                       "Install with: pip install open-clip-torch")
        return False
    except Exception as e:
        logger.warning("CLIP load failed: %s — falling back to time-range retrieval", e)
        return False


def _embed_image(pil_image) -> Optional[np.ndarray]:
    """Return CLIP image embedding as numpy float32 array, or None."""
    if not _clip_available:
        return None
    try:
        import torch
        tensor = _clip_preprocess(pil_image).unsqueeze(0)
        with torch.no_grad():
            emb = _clip_model.encode_image(tensor)
            emb = emb / emb.norm(dim=-1, keepdim=True)  # L2 normalise
        return emb.squeeze().cpu().numpy().astype(np.float32)
    except Exception as e:
        logger.warning("CLIP image embed failed: %s", e)
        return None


def _embed_text(query: str) -> Optional[np.ndarray]:
    """Return CLIP text embedding as numpy float32 array, or None."""
    if not _clip_available:
        return None
    try:
        import torch
        tokens = _clip_tokenizer([query])
        with torch.no_grad():
            emb = _clip_model.encode_text(tokens)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb.squeeze().cpu().numpy().astype(np.float32)
    except Exception as e:
        logger.warning("CLIP text embed failed: %s", e)
        return None


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))  # both already L2-normalised


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class StoredFrame:
    timestamp: float
    thread_id: str
    b64_jpeg: str                          # compressed JPEG
    embedding: Optional[np.ndarray] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class FrameStore:
    """Thread-safe store of motion-triggered frames with CLIP embeddings."""

    def __init__(self):
        self._lock = threading.Lock()
        # thread_id -> list[StoredFrame], sorted by timestamp
        self._frames: dict[str, list[StoredFrame]] = {}
        _load_clip()  # attempt CLIP load at construction time

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, thread_id: str, b64_jpeg: str, timestamp: float | None = None) -> StoredFrame:
        """Compress, embed, and store a frame. Evicts frames outside the 5-min window."""
        ts = timestamp or time.time()

        # Re-compress to save memory
        compressed = _compress(b64_jpeg, quality=_JPEG_QUALITY)

        # Generate CLIP embedding
        embedding = None
        if _clip_available:
            pil = _b64_to_pil(compressed)
            if pil:
                embedding = _embed_image(pil)

        frame = StoredFrame(
            timestamp=ts,
            thread_id=thread_id,
            b64_jpeg=compressed,
            embedding=embedding,
        )

        cutoff = ts - _WINDOW_SECONDS
        with self._lock:
            frames = self._frames.setdefault(thread_id, [])
            frames.append(frame)
            # Evict old frames
            self._frames[thread_id] = [f for f in frames if f.timestamp >= cutoff]

        logger.debug("FrameStore[%s]: stored frame ts=%.0f clip=%s",
                     thread_id, ts, embedding is not None)
        return frame

    # ------------------------------------------------------------------
    # Read — semantic search
    # ------------------------------------------------------------------

    def search(
        self,
        thread_id: str,
        query: str,
        top_k: int = 3,
        time_start: float | None = None,
        time_end: float | None = None,
    ) -> list[StoredFrame]:
        """Return top_k frames most semantically similar to query.

        Falls back to evenly-sampled frames if CLIP is unavailable.
        Optionally filters to [time_start, time_end].
        """
        with self._lock:
            frames = list(self._frames.get(thread_id, []))

        if time_start is not None:
            frames = [f for f in frames if f.timestamp >= time_start]
        if time_end is not None:
            frames = [f for f in frames if f.timestamp <= time_end]

        if not frames:
            return []

        # CLIP path
        if _clip_available:
            text_emb = _embed_text(query)
            if text_emb is not None:
                scored = [
                    (f, _cosine_sim(text_emb, f.embedding))
                    for f in frames
                    if f.embedding is not None
                ]
                if scored:
                    scored.sort(key=lambda x: x[1], reverse=True)
                    return [f for f, _ in scored[:top_k]]

        # Fallback: evenly sample
        return _sample(frames, top_k)

    # ------------------------------------------------------------------
    # Read — time range
    # ------------------------------------------------------------------

    def get_in_range(
        self, thread_id: str, start: float, end: float
    ) -> list[StoredFrame]:
        with self._lock:
            frames = self._frames.get(thread_id, [])
            return [f for f in frames if start <= f.timestamp <= end]

    def get_latest(self, thread_id: str, count: int = 1) -> list[StoredFrame]:
        with self._lock:
            frames = self._frames.get(thread_id, [])
            return frames[-count:]

    def count(self, thread_id: str) -> int:
        with self._lock:
            return len(self._frames.get(thread_id, []))

    def clip_available(self) -> bool:
        return _clip_available


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compress(b64_jpeg: str, quality: int = 40) -> str:
    """Re-encode a base64 JPEG at lower quality. Returns original on failure."""
    try:
        from PIL import Image
        data = base64.b64decode(b64_jpeg)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning("Frame compression failed: %s — storing original", e)
        return b64_jpeg


def _b64_to_pil(b64_jpeg: str):
    """Decode base64 JPEG to PIL Image. Returns None on failure."""
    try:
        from PIL import Image
        data = base64.b64decode(b64_jpeg)
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None


def _sample(frames: list[StoredFrame], count: int) -> list[StoredFrame]:
    """Evenly sample `count` frames from a list."""
    if len(frames) <= count:
        return frames
    step = len(frames) / count
    return [frames[int(i * step)] for i in range(count)]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_frame_store = FrameStore()


def get_frame_store() -> FrameStore:
    return _frame_store
