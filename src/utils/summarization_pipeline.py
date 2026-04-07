"""Rolling summarization pipeline.

Background thread that fires at each time boundary and compresses:
  raw events → 5min → 10min → 30min → 1hr → 12hr → daily

Each level reads its children (lower-level nodes or raw events),
calls the LLM to summarize, then writes a new MemoryNode.

Watermarks track the last summarized endpoint per (thread_id, level)
so we never double-summarize the same window.
"""

import threading
import time

from langchain_core.messages import HumanMessage, SystemMessage

from src.configs.logging_config import get_logger
from src.llm_config import llm
from src.utils.event_log import get_event_log
from src.utils.frame_buffer import get_all_thread_ids as frame_thread_ids
from src.utils.memory_store import SPAN, Level, get_store

logger = get_logger(__name__)

# Check interval — wake up every 30s and see if any level is due
_TICK_INTERVAL = 30

# Ordered from finest to coarsest; each level feeds the next
_LEVELS: list[Level] = ["5min", "10min", "30min", "1hr", "12hr", "daily"]

# How many children each level consumes from the level below
_CHILDREN_COUNT: dict[Level, int] = {
    "5min":  0,    # consumes raw events (not MemoryNodes)
    "10min": 2,    # consumes 2x 5min nodes
    "30min": 3,    # consumes 3x 10min nodes
    "1hr":   2,    # consumes 2x 30min nodes
    "12hr":  12,   # consumes 12x 1hr nodes
    "daily": 2,    # consumes 2x 12hr nodes
}

_CHILD_LEVEL: dict[Level, Level | None] = {
    "5min":  None,    # raw events
    "10min": "5min",
    "30min": "10min",
    "1hr":   "30min",
    "12hr":  "1hr",
    "daily": "12hr",
}

_SUMMARIZE_SYSTEM = (
    "You are summarizing activity logs for a perceptual AI assistant. "
    "Write a concise summary (2-4 sentences) of the events below. "
    "Keep key actions, people, and objects. Drop trivial repetition. "
    "Use past tense. Be factual."
)


def _build_prompt(level: Level, content: str) -> str:
    window = {
        "5min": "5 minutes",
        "10min": "10 minutes",
        "30min": "30 minutes",
        "1hr": "1 hour",
        "12hr": "12 hours",
        "daily": "full day",
    }[level]
    return (
        f"Summarize the following {window} of activity observations into 2-4 sentences:\n\n"
        f"{content}"
    )


def _call_llm(level: Level, content: str) -> str:
    """Call the LLM to produce a summary. Returns empty string on failure."""
    try:
        messages = [
            SystemMessage(content=_SUMMARIZE_SYSTEM),
            HumanMessage(content=_build_prompt(level, content)),
        ]
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        logger.exception("Summarization LLM call failed for level=%s: %s", level, e)
        return ""


class SummarizationPipeline:
    """Runs a background thread that rolls up memory at each time boundary."""

    def __init__(self):
        self._lock = threading.Lock()
        # (thread_id, level) -> last summarized-until timestamp
        self._watermarks: dict[tuple[str, str], float] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="summarization-pipeline")
        self._thread.start()
        logger.info("SummarizationPipeline started")

    def stop(self):
        self._running = False
        logger.info("SummarizationPipeline stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(self):
        while self._running:
            try:
                self._tick()
            except Exception:
                logger.exception("SummarizationPipeline tick error")
            time.sleep(_TICK_INTERVAL)

    def _tick(self):
        """Check every (thread, level) pair and summarize if a window has closed."""
        now = time.time()
        store = get_store()

        # Collect active thread_ids from both stores
        active_threads = self._active_threads()

        for thread_id in active_threads:
            for level in _LEVELS:
                span = SPAN[level]
                watermark = self._get_watermark(thread_id, level)

                # Window closes when now >= watermark + span
                window_end = watermark + span
                if now < window_end:
                    continue  # window not closed yet

                logger.info("Summarizing %s window for thread=%s [%.0f–%.0f]",
                            level, thread_id, watermark, window_end)

                summary = self._summarize_window(thread_id, level, watermark, window_end)

                if summary:
                    children_ids = self._collect_children_ids(thread_id, level, watermark, window_end)
                    store.add_node(
                        thread_id=thread_id,
                        level=level,
                        start_time=watermark,
                        end_time=window_end,
                        summary=summary,
                        children_ids=children_ids,
                    )
                    logger.info("Created %s MemoryNode for thread=%s", level, thread_id)
                else:
                    logger.debug("No content for %s window, skipping node creation", level)

                # Advance watermark regardless — don't re-process empty windows
                self._set_watermark(thread_id, level, window_end)

    # ------------------------------------------------------------------
    # Summarization per level
    # ------------------------------------------------------------------

    def _summarize_window(
        self, thread_id: str, level: Level, start: float, end: float
    ) -> str:
        """Build content string and call LLM. Returns '' if nothing to summarize."""
        if level == "5min":
            return self._summarize_from_events(thread_id, start, end)
        else:
            return self._summarize_from_nodes(thread_id, level, start, end)

    def _summarize_from_events(self, thread_id: str, start: float, end: float) -> str:
        """5-min level: summarize raw events from the EventLog."""
        event_log = get_event_log()
        events = event_log.get_events_in_range(thread_id, start, end)
        if not events:
            return ""
        content = event_log.format_for_llm(events)
        return _call_llm("5min", content)

    def _summarize_from_nodes(self, thread_id: str, level: Level, start: float, end: float) -> str:
        """Non-raw levels: summarize child MemoryNodes from the store."""
        store = get_store()
        child_level = _CHILD_LEVEL[level]
        children = store.get_nodes_in_range(thread_id, child_level, start, end)
        if not children:
            return ""
        content = "\n\n".join(
            f"[{_fmt_time(n.start_time)}–{_fmt_time(n.end_time)}]\n{n.summary}"
            for n in children
        )
        return _call_llm(level, content)

    def _collect_children_ids(
        self, thread_id: str, level: Level, start: float, end: float
    ) -> list[str]:
        """Return IDs of child nodes that fall within this window."""
        child_level = _CHILD_LEVEL.get(level)
        if child_level is None:
            return []
        store = get_store()
        children = store.get_nodes_in_range(thread_id, child_level, start, end)
        return [n.id for n in children]

    # ------------------------------------------------------------------
    # Watermark management
    # ------------------------------------------------------------------

    def _get_watermark(self, thread_id: str, level: str) -> float:
        """Return the last summarized-until timestamp for (thread_id, level).

        Defaults to now - span, so we start with the most recent window.
        """
        key = (thread_id, level)
        with self._lock:
            if key not in self._watermarks:
                # Start watermark at the most recent window boundary
                now = time.time()
                span = SPAN[level]
                # Align to span boundary
                aligned = now - (now % span)
                self._watermarks[key] = aligned
            return self._watermarks[key]

    def _set_watermark(self, thread_id: str, level: str, ts: float):
        with self._lock:
            self._watermarks[(thread_id, level)] = ts

    # ------------------------------------------------------------------
    # Active thread discovery
    # ------------------------------------------------------------------

    def _active_threads(self) -> set[str]:
        """Collect thread_ids that have any data (events or frames)."""
        threads: set[str] = set()

        # Threads with frames (thread-safe via public API)
        threads.update(frame_thread_ids())

        # Threads with events (thread-safe via public method)
        threads.update(get_event_log().get_all_thread_ids())

        # Threads already being tracked by the pipeline
        with self._lock:
            for thread_id, _ in self._watermarks.keys():
                threads.add(thread_id)

        return threads

    def register_thread(self, thread_id: str):
        """Explicitly register a thread so the pipeline tracks it from startup."""
        now = time.time()
        for level in _LEVELS:
            span = SPAN[level]
            aligned = now - (now % span)
            key = (thread_id, level)
            with self._lock:
                if key not in self._watermarks:
                    self._watermarks[key] = aligned
        logger.debug("Registered thread %s with summarization pipeline", thread_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_pipeline = SummarizationPipeline()


def get_pipeline() -> SummarizationPipeline:
    return _pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_time(ts: float) -> str:
    """Format unix timestamp as HH:MM for display in prompts."""
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
