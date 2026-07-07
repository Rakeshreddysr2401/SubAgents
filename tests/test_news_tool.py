"""News tool: date-stamps the query so cached headlines can't go stale."""

from datetime import date
from unittest.mock import AsyncMock, patch

from src.tools.news_tools import get_latest_news


async def test_news_query_is_date_stamped():
    with patch("src.tools.news_tools.cached_search", new=AsyncMock(return_value="headlines")) as mock:
        result = await get_latest_news.ainvoke({"topic": "AI"})

    assert result == "headlines"
    query = mock.await_args.args[0]
    assert "AI" in query
    assert date.today().isoformat() in query
