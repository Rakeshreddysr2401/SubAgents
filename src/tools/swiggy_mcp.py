"""
Swiggy food tool loader.

Lazily opens an authenticated MCP session on first use and keeps it alive
for the lifetime of the process.  Run auth_swiggy.py once to save a token
before starting the LangGraph server.
"""

import logging
import asyncio
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

    try:
        logger.info("Initialising Swiggy MCP session...")
        _client = await asyncio.to_thread(SwiggyMCPClient)
        # Enter the context manager but deliberately never exit here — session stays alive.
        _session_ctx = _client.session()
        
        # Use wait_for to prevent infinite hang if browser login is needed but ignored
        _session = await asyncio.wait_for(_session_ctx.__aenter__(), timeout=60.0)
        
        # Try loading tools - handle both sync and async return types robustly
        result = load_mcp_tools(_session)
        if asyncio.iscoroutine(result):
            _tools = await result
        else:
            _tools = result
        
        logger.info("Loaded %d Swiggy food tools from MCP", len(_tools))
        return _tools
    except asyncio.TimeoutError:
        logger.error("Timeout initialising Swiggy MCP session. Did you complete the browser login?")
        raise RuntimeError("Swiggy login timeout. Please try again and complete the login in your browser.")
    except Exception as e:
        logger.error("Failed to load Swiggy food tools: %s", e)
        raise


async def close_swiggy_session():
    """Close the Swiggy MCP session and clean up resources."""
    global _session_ctx, _session, _tools, _client
    if _session_ctx is not None:
        logger.info("Closing Swiggy MCP session...")
        await _session_ctx.__aexit__(None, None, None)
        _session_ctx = None
        _session = None
        _tools = None
        _client = None
        logger.info("Swiggy MCP session closed.")
