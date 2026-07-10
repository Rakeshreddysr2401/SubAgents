"""Progress lines from long-running tools → {"progress": ...} SSE events.

Uses LangGraph's custom stream channel (get_stream_writer). Safe to call from
anywhere: outside a graph run (unit tests, REST handlers) it's a no-op.
"""

import logging

logger = logging.getLogger(__name__)


def emit_progress(text: str) -> None:
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        return  # not inside a graph run
    if writer is None:
        return
    try:
        writer({"progress": text})
    except Exception as e:  # never let UX sugar break a tool
        logger.debug("progress emit failed: %s", e)
