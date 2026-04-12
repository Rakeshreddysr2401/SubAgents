"""Memory query tool — text log of observations from the last 5 minutes.

recall_recent reads directly from the EventLog (in-memory, sub-millisecond).
No LLaVA call, no camera access. Fast.

Use this first. Only call look_now if this log doesn't answer the question.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.configs.logging_config import get_logger
from src.utils.event_log import get_event_log

logger = get_logger(__name__)

_WINDOW_SECONDS = 300  # 5 minutes


@tool
def recall_recent(query: str, config: RunnableConfig) -> str:
    """Read the text log of everything observed in the last 5 minutes.

    The log contains LLaVA captions captured whenever motion was detected —
    each entry describes people, clothing colors, objects, actions, and the setting.

    Use this for:
    - "what happened in the last 5 minutes?"
    - "was there a person in the room?"
    - "what was I doing earlier?"
    - "did you see anyone?"
    - any question about recent activity or past observations

    This is the FAST path — no camera call, reads text only.
    If the answer isn't in this log, use look_now to examine a live frame.

    Args:
        query: The user's question about recent activity.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    event_log = get_event_log()

    events = event_log.get_recent_events(thread_id, seconds=_WINDOW_SECONDS)
    count = len(events)

    logger.info("recall_recent: thread=%s events=%d", thread_id, count)

    if count == 0:
        return (
            "No observations in the last 5 minutes. "
            "Either no motion was detected or the camera is not connected."
        )

    text = event_log.format_for_llm(events)
    return (
        f"Observations from the last 5 minutes ({count} captured):\n\n"
        f"{text}"
    )
