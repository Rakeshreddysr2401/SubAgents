"""Shared async Redis client.

A single lazily-created connection pool used by the frame buffer, rate limiter,
and web-search cache. Independent of app.state so tools (which only receive a
RunnableConfig) can use it too.
"""

import redis.asyncio as aioredis

from src.configs.settings import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
