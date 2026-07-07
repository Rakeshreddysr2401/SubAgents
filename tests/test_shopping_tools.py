"""Shopping tools: name resolution, ambiguity, update events, swiggy compose fix."""

import json

import pytest

from src.services.event_broker import get_broker, reset_broker
from src.services.shopping_store import InMemoryShoppingStore, configure_shopping_store
from src.tools.shopping_tools import (
    add_shopping_item,
    list_shopping_items,
    mark_item_purchased,
    remove_shopping_item,
)


@pytest.fixture(autouse=True)
def fresh_state():
    reset_broker()
    store = InMemoryShoppingStore()
    configure_shopping_store(store)
    yield store
    configure_shopping_store(None)
    reset_broker()


def _config(user_id: str = "u1") -> dict:
    return {"configurable": {"user_id": user_id, "thread_id": "t1"}}


async def test_add_and_list(fresh_state):
    q = get_broker().subscribe("u1")

    result = await add_shopping_item.ainvoke(
        {"name": "chintol soap", "quantity": "2 packs"}, config=_config()
    )
    assert "chintol soap" in result
    assert json.loads(q.get_nowait()) == {"type": "shopping_updated"}

    listing = await list_shopping_items.ainvoke({}, config=_config())
    assert "chintol soap" in listing and "2 packs" in listing


async def test_mark_purchased_by_partial_name(fresh_state):
    await fresh_state.add("u1", "chintol soap")

    result = await mark_item_purchased.ainvoke({"name": "soap"}, config=_config())
    assert "Marked as purchased" in result

    items = await fresh_state.list_for_user("u1")
    assert items[0].purchased is True


async def test_ambiguous_name_returns_candidates(fresh_state):
    await fresh_state.add("u1", "hand soap")
    await fresh_state.add("u1", "dish soap")

    result = await mark_item_purchased.ainvoke({"name": "soap"}, config=_config())
    assert "Multiple items match" in result
    assert "hand soap" in result and "dish soap" in result


async def test_unpurchased_match_preferred_over_purchased(fresh_state):
    old = await fresh_state.add("u1", "soap")
    await fresh_state.set_purchased(old.id, "u1", True)
    await fresh_state.add("u1", "soap")  # re-added after purchase

    result = await mark_item_purchased.ainvoke({"name": "soap"}, config=_config())
    # Not ambiguous: the single unpurchased item wins.
    assert "Marked as purchased" in result


async def test_remove_missing_item(fresh_state):
    result = await remove_shopping_item.ainvoke({"name": "ghost"}, config=_config())
    assert "No shopping-list item" in result


def test_apply_swiggy_tools_keeps_base_tools():
    """The startup MCP injection must compose with, not overwrite, the base
    (shopping) tools — this was a real footgun."""
    import src.tools as tools_pkg

    before = list(tools_pkg.SWIGGY_TOOLS)
    try:
        fake_mcp = ["mcp_tool_sentinel"]
        tools_pkg.apply_swiggy_tools(fake_mcp)
        names = [getattr(t, "name", t) for t in tools_pkg.SWIGGY_TOOLS]
        assert "mcp_tool_sentinel" in names
        assert "add_shopping_item" in names
        assert "list_shopping_items" in names
    finally:
        tools_pkg.apply_swiggy_tools([])
        tools_pkg.SWIGGY_TOOLS[:] = before
