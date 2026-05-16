"""
Swiggy food tool loader.

Lazily opens an authenticated MCP session on first use and keeps it alive
for the lifetime of the process.  Run auth_swiggy.py once to save a token
before starting the LangGraph server.
"""

import logging
from langchain_mcp_adapters.tools import load_mcp_tools
from src.utils.swiggy_mcp_client import SwiggyMCPClient

logger = logging.getLogger(__name__)

_client: SwiggyMCPClient | None = None
_session = None        # raw ClientSession — kept alive intentionally
_session_ctx = None    # async context manager — never exited so session stays open
_tools: list | None = None


async def get_swiggy_food_tools() -> list:
    """Return all 14 Swiggy food tools, initialising the MCP session on first call.

    The session is opened once and reused for every subsequent tool call.
    On first call (no saved token) a browser window opens for Swiggy login.
    """
    global _client, _session, _session_ctx, _tools

    if _tools is not None:
        return _tools

    _client = SwiggyMCPClient()
    # Enter the context manager but deliberately never exit — session stays alive.
    _session_ctx = _client.session()
    _session = await _session_ctx.__aenter__()
    _tools = await load_mcp_tools(_session)
    logger.info("Loaded %d Swiggy food tools from MCP", len(_tools))
    return _tools
