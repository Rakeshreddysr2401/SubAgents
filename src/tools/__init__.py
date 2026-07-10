from src.tools.vision_tools import capture_webcam
from src.tools.system_tools import get_system_info, open_mac_app
from src.tools.reminder_tools import cancel_reminder, create_reminder, list_reminders
from src.tools.guardian_tools import disable_guardian, enable_guardian
from src.tools.location_tools import get_current_location
from src.tools.music_tools import list_music_stations, play_music, stop_music
from src.tools.news_tools import get_latest_news
from src.tools.order_tools import set_active_order
from src.tools.ui_tools import ask_user_choice
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
    ask_user_choice,
]

# Non-MCP tools the ordering agents always carry. apply_mcp_tools() COMPOSES
# these with the MCP tools (it must never plain-overwrite the lists, or
# everything registered at import time would be silently wiped at startup).
_SWIGGY_BASE_TOOLS = [*SHOPPING_TOOLS, get_current_location, set_active_order, ask_user_choice]
_INSTAMART_BASE_TOOLS = [*SHOPPING_TOOLS, get_current_location, set_active_order, ask_user_choice]
_DINEOUT_BASE_TOOLS = [ask_user_choice]

SWIGGY_TOOLS = [*_SWIGGY_BASE_TOOLS]
INSTAMART_TOOLS = [*_INSTAMART_BASE_TOOLS]
DINEOUT_TOOLS = [*_DINEOUT_BASE_TOOLS]

# The food and instamart MCP servers SHARE several tool names (get_addresses,
# confirm_order, get_payment_options, …), so the tracker can't carry both full
# sets — one ToolNode would hold ambiguous duplicates. This read-only tracking
# subset doesn't collide; ordering tools stay with the owning agent.
_TRACKING_TOOL_NAMES = {
    "get_food_orders", "get_food_order_details",           # food
    "track_food_order", "get_food_delivery_status",
    "get_orders", "track_order", "get_delivery_status",    # instamart
}

TRACKER_TOOLS = [set_active_order, ask_user_choice]


def apply_mcp_tools(
    food_tools: list, instamart_tools: list | None = None, dineout_tools: list | None = None
) -> None:
    """Inject MCP tools (loaded async at startup) into the shared tool sets.

    Mutates the lists in place; the graph must be built AFTER this runs so the
    agents snapshot the full lists. Idempotent.
    """
    instamart_tools = instamart_tools or []
    dineout_tools = dineout_tools or []
    SWIGGY_TOOLS[:] = [*_SWIGGY_BASE_TOOLS, *food_tools]
    INSTAMART_TOOLS[:] = [*_INSTAMART_BASE_TOOLS, *instamart_tools]
    DINEOUT_TOOLS[:] = [*_DINEOUT_BASE_TOOLS, *dineout_tools]
    TRACKER_TOOLS[:] = [
        set_active_order,
        ask_user_choice,
        *(
            t
            for t in [*food_tools, *instamart_tools]
            if getattr(t, "name", None) in _TRACKING_TOOL_NAMES
        ),
    ]


def apply_swiggy_tools(mcp_tools: list) -> None:
    """Legacy alias: food-only injection (kept for older call sites/tests)."""
    apply_mcp_tools(mcp_tools)
