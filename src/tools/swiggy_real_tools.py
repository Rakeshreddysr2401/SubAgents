import asyncio
from typing import Any, Optional
from langchain_core.tools import tool
from src.utils.swiggy_mcp_client import SwiggyMCPClient
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

# Global client instances for reuse
_food_client: Optional[SwiggyMCPClient] = None

async def get_food_client() -> SwiggyMCPClient:
    """Lazy initialization of the Swiggy Food MCP client."""
    global _food_client
    if _food_client is None:
        _food_client = SwiggyMCPClient("https://mcp.swiggy.com/food")
    return _food_client

async def _execute_mcp_tool(tool_name: str, arguments: dict, fallback_msg: str = "No data found.") -> str:
    """Helper to execute an MCP tool via the Swiggy client and handle boilerplate session logic."""
    try:
        client = await get_food_client()
        async with client.session() as session:
            result = await session.call_tool(tool_name, arguments)
            if result and hasattr(result, "content") and result.content:
                return str(result.content[0].text)
            return fallback_msg
    except Exception as e:
        logger.error(f"Error executing Swiggy tool '{tool_name}': {e}")
        return f"Error executing {tool_name}: {e}. Please ensure you are authenticated."

@tool
async def swiggy_get_addresses() -> str:
    """Get the user's saved delivery addresses from Swiggy."""
    return await _execute_mcp_tool("get_addresses", {}, "No addresses found.")

@tool
async def swiggy_search_restaurants(query: str) -> str:
    """Search for restaurants on Swiggy by name or cuisine.
    Args:
        query: Search term (e.g. 'Biryani', 'Pizza', 'Truffles')
    """
    return await _execute_mcp_tool("search_restaurants", {"query": query}, "No restaurants found.")

@tool
async def swiggy_get_menu(restaurant_id: str) -> str:
    """Get the menu for a specific Swiggy restaurant.
    Args:
        restaurant_id: The ID of the restaurant (from search results)
    """
    return await _execute_mcp_tool("get_restaurant_menu", {"restaurant_id": restaurant_id}, "Menu not found.")

@tool
async def swiggy_update_cart(restaurant_id: str, items: list[dict]) -> str:
    """Add items to the Swiggy food cart or update quantities.
    Args:
        restaurant_id: The ID of the restaurant.
        items: List of items to add, e.g. [{"item_id": "123", "quantity": 1}]
    """
    return await _execute_mcp_tool(
        "update_food_cart", 
        {"restaurant_id": restaurant_id, "items": items}, 
        "Cart updated successfully."
    )

@tool
async def swiggy_track_order(order_id: str) -> str:
    """Track the status of an active Swiggy food order.
    Args:
        order_id: The ID of the order to track.
    """
    return await _execute_mcp_tool("track_food_order", {"order_id": order_id}, "Order info not found.")

REAL_SWIGGY_TOOLS = [
    swiggy_get_addresses,
    swiggy_search_restaurants,
    swiggy_get_menu,
    swiggy_update_cart,
    swiggy_track_order
]
