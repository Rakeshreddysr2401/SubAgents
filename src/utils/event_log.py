"""Raw event log — timestamped captions from motion-triggered VLM.

Each entry represents a moment when the camera detected motion and LLaVA
produced a caption. This is the finest granularity of the memory hierarchy
and the source material that gets compressed into 5-min summaries.

Structure:
  Event(id, timestamp, description, thread_id, tags)
    │
    └── gets summarized into MemoryNode(level="5min") every 5 minutes
"""

import threading
import time
import uuid
from dataclasses import dataclass, field

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

# Raw events older than this are evicted from memory (raw frames cover this window)
_RETENTION_SECONDS = 3 * 3600  # 3 hours


@dataclass
class Event:
    id: str
    timestamp: float        # unix timestamp
    description: str        # VLM caption
    thread_id: str
    tags: list[str] = field(default_factory=list)  # e.g. ["motion", "person", "audio"]


class EventLog:
    """Thread-safe log of raw perceptual events, keyed by thread_id."""

    def __init__(self):
        self._lock = threading.Lock()
        # thread_id -> list[Event], kept sorted by timestamp
        self._logs: dict[str, list[Event]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log(self, thread_id: str, description: str, tags: list[str] | None = None) -> Event:
        """Append a new event to the log. Returns the created Event."""
        event = Event(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            description=description,
            thread_id=thread_id,
            tags=tags or [],
        )
        with self._lock:
            if thread_id not in self._logs:
                self._logs[thread_id] = []
            self._logs[thread_id].append(event)
        logger.debug("EventLog[%s]: logged event — %s", thread_id, description[:80])
        return event

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_events_in_range(
        self,
        thread_id: str,
        start: float,
        end: float,
    ) -> list[Event]:
        """Return events within [start, end] unix timestamps, ordered by time."""
        with self._lock:
            events = self._logs.get(thread_id, [])
            return [e for e in events if start <= e.timestamp <= end]

    def get_recent_events(self, thread_id: str, seconds: int = 60) -> list[Event]:
        """Return events from the last `seconds` seconds."""
        cutoff = time.time() - seconds
        return self.get_events_in_range(thread_id, cutoff, time.time())

    def get_unsummarized_events(
        self,
        thread_id: str,
        since: float,
        until: float,
    ) -> list[Event]:
        """Return events in [since, until] that haven't been rolled into a summary yet.

        Alias for get_events_in_range — the summarization pipeline tracks
        its own watermark externally.
        """
        return self.get_events_in_range(thread_id, since, until)

    def format_for_llm(self, events: list[Event]) -> str:
        """Format a list of events into a readable string for LLM summarization."""
        if not events:
            return "No events recorded."
        lines = []
        for e in events:
            elapsed = int(time.time() - e.timestamp)
            tag_str = f" [{', '.join(e.tags)}]" if e.tags else ""
            lines.append(f"[{elapsed}s ago]{tag_str} {e.description}")
        return "\n".join(lines)

    def format_recent_for_llm(self, thread_id: str, seconds: int = 300) -> str:
        """Convenience: format the last `seconds` seconds of events for LLM context."""
        events = self.get_recent_events(thread_id, seconds)
        return self.format_for_llm(events)

    def has_events_since(self, thread_id: str, since: float) -> bool:
        with self._lock:
            events = self._logs.get(thread_id, [])
            return any(e.timestamp >= since for e in events)

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def get_all_thread_ids(self) -> list[str]:
        """Return a snapshot of all thread IDs that have logged events."""
        with self._lock:
            return list(self._logs.keys())

    def evict_expired(self) -> int:
        """Remove events older than _RETENTION_SECONDS. Returns count removed."""
        cutoff = time.time() - _RETENTION_SECONDS
        removed = 0
        with self._lock:
            for thread_id in list(self._logs.keys()):
                before = len(self._logs[thread_id])
                self._logs[thread_id] = [
                    e for e in self._logs[thread_id] if e.timestamp >= cutoff
                ]
                removed += before - len(self._logs[thread_id])
        if removed:
            logger.debug("EventLog: evicted %d expired events", removed)
        return removed


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_event_log = EventLog()


def get_event_log() -> EventLog:
    return _event_log
