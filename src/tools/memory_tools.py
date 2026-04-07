"""Memory query tools for the perceptual agent.

Two tools:
  recall_events        — broad/temporal queries, walks the summary tree
  visual_detail_query  — fine-grained detail queries, re-asks LLaVA on raw frames

The LLM (supervisor) decides which tool to call based on the question type.
recall_events is the fast path (text only).
visual_detail_query is the fallback when text summaries can't answer.
"""

import re
import time

import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.configs.logging_config import get_logger
from src.llm_config import OLLAMA_BASE_URL
from src.utils.event_log import get_event_log
from src.utils.frame_buffer import get_frames_last_n_seconds
from src.utils.frame_store import get_frame_store
from src.utils.memory_store import Level, get_store

logger = get_logger(__name__)

OLLAMA_VISION_MODEL = "llava"

# Ordered coarsest → finest for top-down search
_LEVELS_COARSE_FIRST: list[Level] = ["daily", "12hr", "1hr", "30min", "10min", "5min"]


# ---------------------------------------------------------------------------
# Time hint parser
# ---------------------------------------------------------------------------

def _parse_time_window(query: str) -> tuple[float, float]:
    """
    Parse natural language time references from a query.
    Returns (start_unix, end_unix).

    Examples:
      "just now" / "right now"     → last 60s
      "a minute ago"               → last 2 min
      "5 minutes ago"              → last 10 min window
      "this morning"               → today 06:00–12:00
      "this afternoon"             → today 12:00–18:00
      "an hour ago"                → last 2 hrs
      "today"                      → since midnight
      "yesterday"                  → previous day
      default                      → last 30 min
    """
    now = time.time()
    q = query.lower()

    if any(p in q for p in ["just now", "right now", "currently", "at the moment"]):
        return now - 60, now

    m = re.search(r"(\d+)\s*min", q)
    if m:
        mins = int(m.group(1))
        return now - (mins * 2 * 60), now  # window = 2x the mentioned time

    if "hour ago" in q or "an hour" in q:
        return now - 7200, now

    m = re.search(r"(\d+)\s*hour", q)
    if m:
        hrs = int(m.group(1))
        return now - (hrs * 2 * 3600), now

    if "this morning" in q:
        import datetime
        today = datetime.date.today()
        start = time.mktime(datetime.datetime(today.year, today.month, today.day, 6, 0).timetuple())
        end = time.mktime(datetime.datetime(today.year, today.month, today.day, 12, 0).timetuple())
        return start, min(end, now)

    if "this afternoon" in q:
        import datetime
        today = datetime.date.today()
        start = time.mktime(datetime.datetime(today.year, today.month, today.day, 12, 0).timetuple())
        end = time.mktime(datetime.datetime(today.year, today.month, today.day, 18, 0).timetuple())
        return start, min(end, now)

    if "today" in q:
        import datetime
        today = datetime.date.today()
        start = time.mktime(datetime.datetime(today.year, today.month, today.day, 0, 0).timetuple())
        return start, now

    if "yesterday" in q:
        import datetime
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        start = time.mktime(datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0).timetuple())
        end = start + 86400
        return start, end

    # Default: last 30 minutes
    return now - 1800, now


def _pick_start_level(start: float, end: float) -> Level:
    """
    Pick the coarsest summary level that fits the requested time window.
    Larger windows → start higher in the hierarchy.
    """
    span = end - start
    if span >= 12 * 3600:
        return "daily"
    if span >= 3600:
        return "12hr"
    if span >= 1800:
        return "1hr"
    if span >= 600:
        return "30min"
    if span >= 300:
        return "10min"
    return "5min"


def _format_nodes(nodes) -> str:
    if not nodes:
        return ""
    import datetime
    lines = []
    for n in nodes:
        t = datetime.datetime.fromtimestamp(n.start_time).strftime("%H:%M")
        lines.append(f"[{t}] {n.summary}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def recall_events(query: str, config: RunnableConfig) -> str:
    """Recall what happened over a time period by searching memory summaries.

    Use this for broad or temporal questions such as:
    - "what happened just now / in the last 5 minutes / this morning?"
    - "was anyone in the room earlier?"
    - "what was I doing an hour ago?"
    - "summarise today's activity"

    The tool starts at the coarsest matching summary level and drills down
    into finer-grained summaries if available. For pixel-level detail
    (counting objects, reading text, identifying specific features) use
    visual_detail_query instead.

    Args:
        query: The user's question about past activity.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    store = get_store()
    event_log = get_event_log()

    start, end = _parse_time_window(query)
    start_level = _pick_start_level(start, end)

    logger.info("recall_events: thread=%s level=%s window=[%.0f,%.0f]",
                thread_id, start_level, start, end)

    # Walk from start_level all the way down to 5min, collecting every level
    # that has data. This gives the agent both the big picture (coarse) and
    # fine-grained detail in one response.
    collected: list[str] = []
    levels_to_try = _LEVELS_COARSE_FIRST[_LEVELS_COARSE_FIRST.index(start_level):]

    for level in levels_to_try:
        nodes = store.get_nodes_in_range(thread_id, level, start, end)
        if nodes:
            section = _format_nodes(nodes)
            collected.append(f"=== {level} summaries ===\n{section}")
        # Always continue drilling — don't break on first hit

    # Always include raw events for the most recent 5 minutes as grounding
    raw_events = event_log.get_recent_events(thread_id, seconds=300)
    if raw_events:
        raw_text = event_log.format_for_llm(raw_events)
        collected.append(f"=== raw observations (last 5 min) ===\n{raw_text}")

    if not collected:
        return (
            "No memory available for that time period. "
            "Either no activity was detected or the window is outside retention."
        )

    return "\n\n".join(collected)


@tool
def visual_detail_query(query: str, config: RunnableConfig) -> str:
    """Answer fine-grained visual detail questions by re-examining raw camera frames.

    Use this when the question requires pixel-level detail that text summaries
    cannot answer, such as:
    - "how many buttons does his shirt have?"
    - "was she wearing a watch?"
    - "what does the label on that bottle say?"
    - "what color was the bag?"
    - "how many people were in the room?"

    The tool retrieves the most relevant frames from the rolling frame buffer
    and sends them to the vision model with the specific question.

    Args:
        query: The specific visual detail question to answer.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    start, end = _parse_time_window(query)
    logger.info("visual_detail_query: thread=%s window=[%.0f,%.0f] query=%s",
                thread_id, start, end, query[:80])

    frame_store = get_frame_store()

    # CLIP semantic search path (preferred)
    if frame_store.clip_available():
        results = frame_store.search(thread_id, query, top_k=3, time_start=start, time_end=end)
        if not results:
            # Widen to full buffer if time-window has nothing
            results = frame_store.search(thread_id, query, top_k=3)
        if results:
            frames_to_send = [f.b64_jpeg for f in results]
            source_note = f"Analysing {len(frames_to_send)} semantically relevant frame(s) via CLIP search."
        else:
            frames_to_send = []
            source_note = ""
    else:
        frames_to_send = []
        source_note = ""

    # Fallback: time-range from FrameStore, then raw frame_buffer
    if not frames_to_send:
        stored = frame_store.get_in_range(thread_id, start, end)
        if stored:
            sampled = _sample_frames([f.b64_jpeg for f in stored], max_count=3)
            frames_to_send = sampled
            source_note = f"Analysing {len(frames_to_send)} frame(s) from the requested time window."
        else:
            recent = get_frames_last_n_seconds(thread_id, seconds=300)
            if not recent:
                return (
                    "No camera frames available for that time window. "
                    "The frame buffer only retains the last 5 minutes. "
                    "Try asking about more recent events."
                )
            frames_to_send = _sample_frames(recent, max_count=3)
            source_note = "Using most recent available frames (requested window has no frames)."

    logger.info("visual_detail_query: sending %d frames to LLaVA", len(frames_to_send))

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": query,
                "images": frames_to_send,
                "stream": False,
            },
            timeout=45,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        if not answer:
            return "Vision model returned no response."
        return f"{source_note}\n\n{answer}"

    except requests.ConnectionError:
        return f"Vision service (Ollama) is not reachable at {OLLAMA_BASE_URL}."
    except requests.Timeout:
        return "Vision service timed out. The model may still be loading."
    except Exception as e:
        logger.exception("visual_detail_query error: %s", e)
        return f"Visual analysis failed: {e}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_frames(frames: list[str], max_count: int = 3) -> list[str]:
    """Evenly sample up to max_count frames from a list."""
    if len(frames) <= max_count:
        return frames
    step = len(frames) / max_count
    return [frames[int(i * step)] for i in range(max_count)]
