"""Swiggy Food MCP tool loading.

`load_swiggy_tools()` is the canonical async entry point — called from the
FastAPI lifespan. It degrades gracefully: any failure (network, auth, timeout)
returns [] and logs a warning so the app always starts.

"""

import asyncio
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.configs.settings import get_settings

logger = logging.getLogger(__name__)


async def _fetch_food_tools() -> list:
    s = get_settings()
    headers = {}
    if s.swiggy_access_token:
        headers["Authorization"] = f"Bearer {s.swiggy_access_token}"

    client = MultiServerMCPClient(
        {
            "swiggy_food": {
                "transport": "streamable_http",
                "url": s.swiggy_food_mcp_url,
                "headers": headers,
            }
        }
    )
    return await client.get_tools()


async def load_swiggy_tools(timeout: float | None = None) -> list:
    """Load Swiggy Food MCP tools, returning [] on any failure."""
    if timeout is None:
        timeout = get_settings().mcp_load_timeout_seconds
    try:
        tools = await asyncio.wait_for(_fetch_food_tools(), timeout=timeout)
        logger.info("Loaded %d Swiggy Food MCP tools", len(tools))
        return tools
    except Exception as e:
        logger.warning("Swiggy Food MCP unavailable — tools disabled: %s", e)
        return []


