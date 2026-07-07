from src.tools.vision_tools import capture_webcam
from src.tools.system_tools import get_system_info, open_mac_app
from src.tools.reminder_tools import cancel_reminder, create_reminder, list_reminders
from src.tools.guardian_tools import disable_guardian, enable_guardian
from src.tools.location_tools import get_current_location
from src.tools.music_tools import list_music_stations, play_music, stop_music
from src.tools.news_tools import get_latest_news
from src.tools.shopping_tools import (
    add_shopping_item,
    list_shopping_items,
    mark_item_purchased,
    remove_shopping_item,
)
from src.rag.web_cache import cached_web_search
from src.rag.retrieval_tools import recall_history, search_documents

from src.configs.settings import get_settings

# Web search is offered only when a Tavily key is configured; the cached
# wrapper still degrades gracefully if the key later becomes invalid.
_WEB_TOOLS = (
    [cached_web_search, get_latest_news] if get_settings().tavily_api_key else []
)

REMINDER_TOOLS = [create_reminder, list_reminders, cancel_reminder]
SHOPPING_TOOLS = [add_shopping_item, list_shopping_items, mark_item_purchased, remove_shopping_item]
MUSIC_TOOLS = [play_music, stop_music, list_music_stations]
GUARDIAN_TOOLS = [enable_guardian, disable_guardian]

# Per-agent tool sets (handoff tools are appended in src/graph/swarm.py).
# Swiggy MCP tools are injected at startup via apply_swiggy_tools() —
# no import-time network calls.
CONVERSATION_TOOLS = [
    capture_webcam,
    get_system_info,
    open_mac_app,
    get_current_location,
    search_documents,
    recall_history,
    *REMINDER_TOOLS,
    *SHOPPING_TOOLS,
    *MUSIC_TOOLS,
    *GUARDIAN_TOOLS,
    *_WEB_TOOLS,
]

# Non-MCP tools the swiggy agent always carries. apply_swiggy_tools() COMPOSES
# these with the MCP tools (it must never plain-overwrite SWIGGY_TOOLS, or
# everything registered at import time would be silently wiped at startup).
_SWIGGY_BASE_TOOLS = [*SHOPPING_TOOLS, get_current_location]

SWIGGY_TOOLS = [*_SWIGGY_BASE_TOOLS]

TRACKER_TOOLS = []


def apply_swiggy_tools(mcp_tools: list) -> None:
    """Inject Swiggy MCP tools (loaded async at startup) into the shared tool sets.

    Mutates the lists in place; the graph must be built AFTER this runs so the
    agents snapshot the full lists. Idempotent.
    """
    SWIGGY_TOOLS[:] = [*_SWIGGY_BASE_TOOLS, *mcp_tools]
    TRACKER_TOOLS[:] = list(mcp_tools)
