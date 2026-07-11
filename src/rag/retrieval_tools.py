"""Agent-facing RAG retrieval tools: search_documents, recall_history.

Both scope results to the current user via config["configurable"]["user_id"],
which /chat injects into the run config.
"""

from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.api.auth import DEFAULT_USER
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.rag.store import search_texts

logger = get_logger(__name__)


def _user_id(config: RunnableConfig) -> str:
    return (config.get("configurable") or {}).get("user_id", DEFAULT_USER)


@tool
async def search_documents(query: str, config: RunnableConfig) -> str:
    """Search the user's uploaded documents for information relevant to the query.
    Use this whenever the user asks about the contents of files they have uploaded."""
    from src.tools.progress import emit_progress

    emit_progress("Searching your documents…")
    settings = get_settings()
    hits = await search_texts(
        settings.documents_collection, query, _user_id(config), limit=5
    )
    if not hits:
        return "No relevant content found in the user's uploaded documents."
    lines = []
    for h in hits:
        src = h.get("filename", "document")
        lines.append(f"[{src}] {h.get('text', '')}")
    return "\n\n".join(lines)


@tool
async def recall_history(query: str, config: RunnableConfig) -> str:
    """Recall past conversations or things the user showed the camera earlier.
    Use for questions like 'what did we talk about' or 'what did I show you last week'."""
    from src.tools.progress import emit_progress

    emit_progress("Looking back through our history…")
    settings = get_settings()
    hits = await search_texts(
        settings.history_collection, query, _user_id(config), limit=5
    )
    if not hits:
        return "No relevant past conversation or activity found."
    lines = []
    for h in hits:
        ts = h.get("ts")
        when = ""
        if ts:
            try:
                when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                when = ""
        prefix = f"({when}) " if when else ""
        lines.append(f"{prefix}{h.get('text', '')}")
    return "\n".join(lines)
