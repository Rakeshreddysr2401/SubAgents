"""News tool — date-stamped web search so the semantic cache can't serve
yesterday's headlines as today's."""

from datetime import date

from langchain_core.tools import tool

from src.rag.web_cache import cached_search


@tool
async def get_latest_news(topic: str) -> str:
    """Fetch the latest news on a topic. Summarize the results conversationally
    for the user (they may be listening rather than reading).

    Args:
        topic: What to get news about, e.g. "AI", "cricket", "world news".
    """
    today = date.today().isoformat()
    return await cached_search(f"latest news {topic} {today}")
