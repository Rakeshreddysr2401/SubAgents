"""Location tool: graceful degradation + Nominatim caching."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.tools.location_tools as location_tools
from src.tools.location_tools import get_current_location, reverse_geocode


@pytest.fixture(autouse=True)
def fake_redis():
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("src.services.redis_client.get_redis", return_value=redis):
        yield redis


def _response(display_name: str | None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={"display_name": display_name} if display_name else {})
    return resp


def _client_returning(resp):
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


async def test_no_location_in_config_is_graceful():
    result = await get_current_location.ainvoke(
        {}, config={"configurable": {"user_id": "u1", "location": None}}
    )
    assert "Location not available" in result


async def test_reverse_geocode_formats_and_caches(fake_redis):
    ctx, client = _client_returning(_response("MG Road, Bengaluru, India"))
    location_tools._last_call = 0.0

    with patch("src.tools.location_tools.httpx.AsyncClient", return_value=ctx):
        first = await reverse_geocode(12.9716, 77.5946)
        second = await reverse_geocode(12.9716, 77.5946)

    assert "MG Road" in first and "12.97160" in first
    assert second == first
    assert client.get.await_count == 1  # second call served from Redis cache


async def test_reverse_geocode_failure_returns_raw_coords(fake_redis):
    ctx, client = _client_returning(None)
    client.get = AsyncMock(side_effect=RuntimeError("network down"))
    location_tools._last_call = 0.0

    with patch("src.tools.location_tools.httpx.AsyncClient", return_value=ctx):
        result = await reverse_geocode(12.9716, 77.5946)

    assert result == "12.97160, 77.59460"


async def test_tool_reads_location_from_config(fake_redis):
    ctx, _ = _client_returning(_response("Somewhere"))
    location_tools._last_call = 0.0

    with patch("src.tools.location_tools.httpx.AsyncClient", return_value=ctx):
        result = await get_current_location.ainvoke(
            {},
            config={"configurable": {"user_id": "u1", "location": {"lat": 1.0, "lon": 2.0, "accuracy_m": 10}}},
        )

    assert "Somewhere" in result
