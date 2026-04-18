"""Memory query tool — text log of observations from the last 5 minutes.

recall_recent reads the EventLog (moondream captions) and the YOLO-detected
objects from frame_store — both are in-memory reads, sub-millisecond.

Use this before look_now. Only escalate to look_now if this log does not
have enough visual detail for the question.
"""

import time
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.configs.logging_config import get_logger
from src.utils.event_log import get_event_log
from src.utils.frame_store import get_frame_store

logger = get_logger(__name__)

_WINDOW_SECONDS = 300  # 5 minutes


@tool
def recall_recent(query: str, config: RunnableConfig) -> str:
    """Read the text log of everything observed in the last 5 minutes.

    Returns:
    - YOLO-detected objects seen across all motion frames in the window
    - Timestamped moondream captions (who was present, what they did, objects)

    Use this for:
    - "what happened in the last 5 minutes?"
    - "was there a person in the room?"
    - "what was I doing earlier?"
    - "did anyone enter or leave?"
    - any question about recent activity or past observations

    This is the FAST path — no camera call, reads text only.
    If the log lacks the visual detail needed, use look_now.

    Args:
        query: The user's question about recent activity.
    """
    thread_id   = config.get("configurable", {}).get("thread_id", "default")
    event_log   = get_event_log()
    frame_store = get_frame_store()

    now    = time.time()
    cutoff = now - _WINDOW_SECONDS

    events = event_log.get_recent_events(thread_id, seconds=_WINDOW_SECONDS)
    frames = frame_store.get_in_range(thread_id, cutoff, now)

    logger.info(
        "recall_recent: thread=%s events=%d yolo_frames=%d",
        thread_id, len(events), len(frames),
    )

    if not events and not frames:
        return (
            "No observations in the last 5 minutes. "
            "Either no motion was detected or the camera is not connected."
        )

    parts: list[str] = []

    # YOLO objects seen across all motion frames in the window
    yolo_objects: list[str] = []
    for f in frames:
        for tag in f.yolo_tags:
            if tag not in yolo_objects:
                yolo_objects.append(tag)

    if yolo_objects:
        parts.append(
            f"Objects detected (YOLO, last 5 min): {', '.join(yolo_objects)}"
        )

    if events:
        caption_text = event_log.format_for_llm(events)
        parts.append(
            f"Observations ({len(events)} captured, last 5 min):\n{caption_text}"
        )

    return "\n\n".join(parts)
