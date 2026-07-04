from src.tools.vision_tools import capture_webcam
from src.tools.system_tools import get_system_info, open_mac_app
from src.rag.web_cache import cached_web_search
from src.rag.retrieval_tools import recall_history, search_documents

from src.configs.settings import get_settings

# Web search is offered only when a Tavily key is configured; the cached
# wrapper still degrades gracefully if the key later becomes invalid.
_WEB_TOOLS = [cached_web_search] if get_settings().tavily_api_key else []

# Per-agent tool sets (handoff tools are appended in src/graph/swarm.py).
# Swiggy MCP tools are injected at startup via apply_swiggy_tools() —
# no import-time network calls.
CONVERSATION_TOOLS = [
    capture_webcam,
    get_system_info,
    open_mac_app,
    search_documents,
    recall_history,
    *_WEB_TOOLS,
]

SWIGGY_TOOLS = []

TRACKER_TOOLS = []


def apply_swiggy_tools(mcp_tools: list) -> None:
    """Inject Swiggy MCP tools (loaded async at startup) into the shared tool sets.

    Mutates the lists in place; the graph must be built AFTER this runs so the
    agents snapshot the full lists. Idempotent.
    """
    SWIGGY_TOOLS[:] = list(mcp_tools)
    TRACKER_TOOLS[:] = list(mcp_tools)
