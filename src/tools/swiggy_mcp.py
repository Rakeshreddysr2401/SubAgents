import os
import asyncio
import logging
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

_FOOD_MCP_URL = os.getenv("SWIGGY_FOOD_MCP_URL", "https://mcp.swiggy.com/food")
_ACCESS_TOKEN = os.getenv("SWIGGY_ACCESS_TOKEN", "")


async def _fetch_food_tools() -> list:
    headers = {}
    if _ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {_ACCESS_TOKEN}"

    client = MultiServerMCPClient(
        {
            "swiggy_food": {
                "transport": "streamable_http",
                "url": _FOOD_MCP_URL,
                "headers": headers,
            }
        }
    )
    return await client.get_tools()


def _load_sync() -> list:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    try:
        if loop is not None and loop.is_running():
            # Inside a running event loop (e.g. LangGraph hot-reload) — use a thread.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _fetch_food_tools()).result()
        else:
            return asyncio.run(_fetch_food_tools())
    except Exception as e:
        logger.warning("Swiggy Food MCP unavailable — tools disabled: %s", e)
        return []


SWIGGY_FOOD_TOOLS: list = _load_sync()
