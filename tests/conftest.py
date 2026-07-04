"""Shared test fixtures.

Strategy:
- LLM: scripted fake chat models injected via the `get_llm` seam
- Redis: fakeredis.aioredis
- Qdrant: AsyncQdrantClient(":memory:")
- Mem0: recording stub
- Checkpointer: MemorySaver
"""

import os

import pytest

# Ensure tests never pick up real infrastructure or keys from .env
os.environ.setdefault("AUTH_DISABLED", "true")
os.environ.setdefault("LLM_PROVIDER", "llama_cpp")


@pytest.fixture
def settings(monkeypatch):
    """Fresh Settings instance (bypasses the lru_cache) for each test."""
    from src.configs.settings import Settings, get_settings

    get_settings.cache_clear()
    yield Settings()
    get_settings.cache_clear()


@pytest.fixture
async def fake_redis():
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
