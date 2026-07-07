"""Shopping-list tools — a structured, persistent list (not just memory).

"remember we need to buy chintol soap" → add_shopping_item. The swiggy agent
consults list_shopping_items before grocery orders and marks items purchased
after ordering them. Items are matched by name (case-insensitive contains);
an ambiguous match returns the candidates so the model can disambiguate.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.services.event_broker import get_broker
from src.services.shopping_store import get_shopping_store


def _user_id(config: RunnableConfig) -> str:
    return config.get("configurable", {}).get("user_id", "default_user")


def _fmt(item) -> str:
    qty = f" ({item.quantity})" if item.quantity else ""
    mark = "x" if item.purchased else " "
    return f"- [{mark}] {item.name}{qty}"


def _notify(user_id: str) -> None:
    get_broker().broadcast({"type": "shopping_updated"}, user_id)


@tool
async def add_shopping_item(name: str, config: RunnableConfig, quantity: str | None = None) -> str:
    """Add an item to the user's shopping list.

    Use this when the user says things like "remember we need to buy X" or
    "add X to the shopping list".

    Args:
        name: The item, e.g. "chintol soap".
        quantity: Optional amount, e.g. "2 packs".
    """
    user_id = _user_id(config)
    item = await get_shopping_store().add(user_id, name.strip(), quantity)
    _notify(user_id)
    qty = f" ({quantity})" if quantity else ""
    return f"Added to the shopping list: {item.name}{qty}"


@tool
async def list_shopping_items(config: RunnableConfig) -> str:
    """Show the user's shopping list ([x] = already purchased). Check this
    before placing grocery orders so nothing needed is missed."""
    items = await get_shopping_store().list_for_user(_user_id(config))
    if not items:
        return "The shopping list is empty."
    return "Shopping list:\n" + "\n".join(_fmt(i) for i in items)


async def _resolve_by_name(user_id: str, name: str):
    """One unpurchased match wins; ambiguity returns the candidate list."""
    matches = await get_shopping_store().find_by_name(user_id, name.strip())
    unpurchased = [m for m in matches if not m.purchased]
    pool = unpurchased or matches
    if not pool:
        return None, f"No shopping-list item matches '{name}'."
    if len(pool) > 1:
        options = ", ".join(m.name for m in pool)
        return None, f"Multiple items match '{name}': {options}. Which one did you mean?"
    return pool[0], None


@tool
async def mark_item_purchased(name: str, config: RunnableConfig) -> str:
    """Mark a shopping-list item as purchased (e.g. right after ordering it)."""
    user_id = _user_id(config)
    item, error = await _resolve_by_name(user_id, name)
    if error:
        return error
    await get_shopping_store().set_purchased(item.id, user_id, True)
    _notify(user_id)
    return f"Marked as purchased: {item.name}"


@tool
async def remove_shopping_item(name: str, config: RunnableConfig) -> str:
    """Remove an item from the shopping list entirely."""
    user_id = _user_id(config)
    item, error = await _resolve_by_name(user_id, name)
    if error:
        return error
    await get_shopping_store().remove(item.id, user_id)
    _notify(user_id)
    return f"Removed from the shopping list: {item.name}"
