"""Frame buffer (Redis + TTL) and rate limiter, backed by fakeredis."""

import pytest


@pytest.fixture
def patched_redis(monkeypatch, fake_redis):
    """Point the shared get_redis() at fakeredis for all services."""
    from src.services import redis_client

    monkeypatch.setattr(redis_client, "get_redis", lambda: fake_redis)
    return fake_redis


async def test_store_and_get_frame(patched_redis):
    from src.services.frame_buffer import get_latest_frame, store_frame

    assert await get_latest_frame("t1") is None
    await store_frame("t1", "BASE64DATA")
    assert await get_latest_frame("t1") == "BASE64DATA"


async def test_frame_has_ttl(patched_redis):
    from src.services.frame_buffer import store_frame

    await store_frame("t1", "X")
    ttl = await patched_redis.ttl("frame:t1")
    assert 0 < ttl <= 120


async def test_clear_frame(patched_redis):
    from src.services.frame_buffer import clear_frame, get_latest_frame, store_frame

    await store_frame("t1", "X")
    await clear_frame("t1")
    assert await get_latest_frame("t1") is None


async def test_rate_limit_trips(patched_redis, monkeypatch):
    from fastapi import HTTPException

    from src.configs.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")

    from src.services.rate_limit import enforce_rate_limit

    for _ in range(3):
        await enforce_rate_limit("chat", "u1")
    with pytest.raises(HTTPException) as exc:
        await enforce_rate_limit("chat", "u1")
    assert exc.value.status_code == 429
    get_settings.cache_clear()
