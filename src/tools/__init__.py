from src.tools.vision_tools import capture_webcam
from src.tools.system_tools import get_system_info, open_mac_app
from src.tools.handover_tool import handover
from src.tools.swiggy_mcp import SWIGGY_FOOD_TOOLS

# Tavily web search — optional, requires TAVILY_API_KEY env var
try:
    from langchain_community.tools.tavily_search import TavilySearchResults
    import os
    if os.getenv("TAVILY_API_KEY"):
        _tavily = TavilySearchResults(max_results=5)
        _TAVILY_TOOLS = [_tavily]
    else:
        _TAVILY_TOOLS = []
except ImportError:
    _TAVILY_TOOLS = []

# Per-agent tool sets
SUPERVISOR_TOOLS = [handover]

CONVERSATION_TOOLS = [capture_webcam, get_system_info, open_mac_app, *_TAVILY_TOOLS, handover]

SWIGGY_TOOLS = [*SWIGGY_FOOD_TOOLS, handover]

TRACKER_TOOLS = [*SWIGGY_FOOD_TOOLS, handover]

# Legacy alias kept for any imports that still reference ALL_TOOLS
ALL_TOOLS = CONVERSATION_TOOLS
