"""MCP provider framework: no-token no-network, guarded tools, staleness,
hot token reload, status shape, tracker whitelist."""

import json

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from src.services import mcp_providers as mcp


class _Args(BaseModel):
    q: str = ""


def _make_tool(name: str, coro) -> StructuredTool:
    return StructuredTool(name=name, description=f"{name} desc", args_schema=_Args, coroutine=coro)


class _BrokerStub:
    def __init__(self):
        self.payloads = []

    def broadcast(self, payload, user_id=None):
        self.payloads.append(payload)
        return 1


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch, tmp_path):
    mcp.reset_state()
    # Point the token file somewhere hermetic and clear the env override.
    monkeypatch.setenv("SUBAGENTS_MCP_TOKENS", str(tmp_path / "mcp_tokens.json"))
    monkeypatch.delenv("SWIGGY_ACCESS_TOKEN", raising=False)
    yield
    mcp.reset_state()


@pytest.fixture
def broker(monkeypatch):
    stub = _BrokerStub()
    monkeypatch.setattr("src.services.event_broker.get_broker", lambda: stub)
    return stub


def _write_token_file(tmp_path, token: str, expires_at: float | None = None):
    entry = {"access_token": token}
    if expires_at:
        entry["expires_at"] = expires_at
    (tmp_path / "mcp_tokens.json").write_text(
        json.dumps({"version": 1, "domains": {"swiggy": entry}})
    )


# ── loading ─────────────────────────────────────────────────────────────────

async def test_no_token_loads_nothing_and_never_touches_network(monkeypatch):
    async def _explode(spec, headers):
        raise AssertionError("network touched without a token")

    monkeypatch.setattr(mcp, "_fetch_tools", _explode)
    assert await mcp.load_provider_tools("swiggy_food") == []
    assert not mcp.provider_ok("swiggy_food")


async def test_load_guards_and_caches(monkeypatch, tmp_path):
    _write_token_file(tmp_path, "tok-1")
    fetches = []

    async def _fake_fetch(spec, headers):
        fetches.append(headers)
        async def impl(**kwargs):
            return "ok"
        return [_make_tool("search_restaurants", impl)]

    monkeypatch.setattr(mcp, "_fetch_tools", _fake_fetch)
    tools = await mcp.load_provider_tools("swiggy_food", timeout=5)
    assert [t.name for t in tools] == ["search_restaurants"]
    assert tools[0].description == "search_restaurants desc"  # schema preserved
    assert fetches[0]["Authorization"] == "Bearer tok-1"
    assert mcp.provider_ok("swiggy_food")
    # Idempotent: second call returns the cache, no second fetch.
    await mcp.load_provider_tools("swiggy_food", timeout=5)
    assert len(fetches) == 1


async def test_load_failure_degrades_to_empty(monkeypatch, tmp_path):
    _write_token_file(tmp_path, "tok-1")

    async def _fail(spec, headers):
        raise RuntimeError("boom")

    monkeypatch.setattr(mcp, "_fetch_tools", _fail)
    assert await mcp.load_provider_tools("swiggy_food", timeout=5) == []
    assert not mcp.provider_ok("swiggy_food")


# ── root cause + guard ──────────────────────────────────────────────────────

def test_root_cause_unwraps_nested_exception_groups():
    import httpx

    leaf = httpx.ConnectError("no route")
    nested = ExceptionGroup("outer", [ExceptionGroup("inner", [leaf])])
    assert mcp._root_cause(nested) is leaf


async def test_guarded_tool_auth_error_marks_stale_and_notifies_once(broker):
    async def _unauthorized(**kwargs):
        raise RuntimeError("401 Unauthorized")

    spec = mcp.PROVIDERS["swiggy_food"]
    guarded = mcp._guard_tool(_make_tool("confirm_order", _unauthorized), spec)

    result = await guarded.coroutine(q="x")
    assert "login has expired" in result  # LLM-speakable, no raise
    assert not mcp.provider_ok("swiggy_food")
    # Sibling providers on the same auth domain go stale together.
    assert "swiggy" in mcp.status()["tokens"]
    assert mcp.status()["tokens"]["swiggy"]["stale"] is True

    # Second failure: no second notification.
    await guarded.coroutine(q="y")
    assert len(broker.payloads) == 1
    assert broker.payloads[0]["type"] == "mcp_auth_expired"


async def test_guarded_tool_other_error_returns_speakable_string(broker):
    async def _flaky(**kwargs):
        raise RuntimeError("500 upstream exploded")

    spec = mcp.PROVIDERS["swiggy_food"]
    guarded = mcp._guard_tool(_make_tool("get_menu", _flaky), spec)
    result = await guarded.coroutine(q="x")
    assert "get_menu call failed" in result
    assert broker.payloads == []  # not an auth problem — no nudge


async def test_guarded_tool_success_passthrough():
    async def _ok(**kwargs):
        return {"items": 3}

    spec = mcp.PROVIDERS["swiggy_food"]
    guarded = mcp._guard_tool(_make_tool("get_cart", _ok), spec)
    assert await guarded.coroutine(q="x") == {"items": 3}


# ── hot token reload ────────────────────────────────────────────────────────

async def test_refresh_tokens_swaps_header_in_place(monkeypatch, tmp_path, broker):
    _write_token_file(tmp_path, "tok-old")

    async def _fake_fetch(spec, headers):
        async def impl(**kwargs):
            return "ok"
        return [_make_tool("search_restaurants", impl)]

    monkeypatch.setattr(mcp, "_fetch_tools", _fake_fetch)
    await mcp.load_provider_tools("swiggy_food", timeout=5)
    headers = mcp._headers["swiggy_food"]
    assert headers["Authorization"] == "Bearer tok-old"

    mcp.mark_domain_stale("swiggy", "401")
    assert not mcp.provider_ok("swiggy_food")

    import os
    import time as _time

    _write_token_file(tmp_path, "tok-new")
    # Ensure the mtime moves forward even on coarse filesystems.
    future = _time.time() + 5
    os.utime(tmp_path / "mcp_tokens.json", (future, future))

    mcp.refresh_tokens_if_changed()
    assert headers["Authorization"] == "Bearer tok-new"  # same dict object
    assert mcp.provider_ok("swiggy_food")  # re-armed


# ── status ──────────────────────────────────────────────────────────────────

async def test_status_shape_never_leaks_tokens(monkeypatch, tmp_path):
    import time as _time

    _write_token_file(tmp_path, "secret-token", expires_at=_time.time() + 3 * 86400)

    async def _fake_fetch(spec, headers):
        async def impl(**kwargs):
            return "ok"
        return [_make_tool("t1", impl)]

    monkeypatch.setattr(mcp, "_fetch_tools", _fake_fetch)
    await mcp.load_provider_tools("swiggy_food", timeout=5)

    st = mcp.status()
    assert st["providers"]["swiggy_food"] == {"tools": 1, "ok": True}
    assert st["providers"]["swiggy_dineout"]["tools"] == 0
    swiggy = st["tokens"]["swiggy"]
    assert swiggy["source"] == "file"
    assert 2.5 < swiggy["days_left"] < 3.5
    assert "secret-token" not in json.dumps(st)


# ── tool-set composition + tracker whitelist ────────────────────────────────

def test_apply_mcp_tools_tracker_whitelist_no_collisions():
    import src.tools as tools_pkg

    async def _impl(**kwargs):
        return "ok"

    # Food and instamart share names — the tracker must only take the
    # non-colliding read-only tracking subset.
    food = [_make_tool(n, _impl) for n in
            ("search_restaurants", "confirm_order", "get_addresses",
             "get_food_orders", "track_food_order")]
    instamart = [_make_tool(n, _impl) for n in
                 ("search_products", "confirm_order", "get_addresses",
                  "get_orders", "track_order")]
    dineout = [_make_tool(n, _impl) for n in ("search_dineout", "book_table")]

    before = (list(tools_pkg.SWIGGY_TOOLS), list(tools_pkg.INSTAMART_TOOLS),
              list(tools_pkg.DINEOUT_TOOLS), list(tools_pkg.TRACKER_TOOLS))
    try:
        tools_pkg.apply_mcp_tools(food, instamart, dineout)

        tracker_names = [t.name for t in tools_pkg.TRACKER_TOOLS]
        assert sorted(tracker_names) == sorted(
            ["set_active_order", "get_food_orders", "track_food_order",
             "get_orders", "track_order"]
        )
        assert len(tracker_names) == len(set(tracker_names))  # no duplicates

        swiggy_names = [t.name for t in tools_pkg.SWIGGY_TOOLS]
        assert "add_shopping_item" in swiggy_names   # base tools survive
        assert "set_active_order" in swiggy_names
        assert "confirm_order" in swiggy_names

        instamart_names = [t.name for t in tools_pkg.INSTAMART_TOOLS]
        assert "list_shopping_items" in instamart_names
        assert "search_products" in instamart_names

        assert [t.name for t in tools_pkg.DINEOUT_TOOLS] == ["search_dineout", "book_table"]
    finally:
        (tools_pkg.SWIGGY_TOOLS[:], tools_pkg.INSTAMART_TOOLS[:],
         tools_pkg.DINEOUT_TOOLS[:], tools_pkg.TRACKER_TOOLS[:]) = before
