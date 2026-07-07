"""Cached web search.

Layered lookup before hitting Tavily:
  1. Redis exact-match cache (this module) — instant, keyed by query hash
  2. Qdrant semantic cache (added in Phase 5) — near-duplicate queries
  3. Live Tavily call, result written back to both layers

Falls back to a plain live call if Tavily/Redis are unavailable.
"""

import hashlib
import json
import time

from langchain_core.tools import tool

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.services import redis_client

logger = get_logger(__name__)

# Fixed pseudo-user so the shared web cache is scoped to one namespace in the
# user-partitioned `search_cache` collection.
_CACHE_NS = "__web_cache__"


def _tavily_client():
    try:
        from tavily import TavilyClient
    except ImportError:
        return None
    key = get_settings().tavily_api_key
    if not key:
        return None
    return TavilyClient(api_key=key)


def _cache_key(query: str) -> str:
    return "tavily:" + hashlib.sha256(query.strip().lower().encode()).hexdigest()


async def _run_tavily(query: str) -> list[dict]:
    client = _tavily_client()
    if client is None:
        return []
    import asyncio

    resp = await asyncio.to_thread(client.search, query=query, max_results=5)
    return resp.get("results", []) if isinstance(resp, dict) else []


def _format(results: list[dict]) -> str:
    if not results:
        return "No web results found."
    lines = []
    for r in results[:5]:
        title = r.get("title", "")
        url = r.get("url", "")
        content = (r.get("content", "") or "")[:300]
        lines.append(f"- {title} ({url})\n  {content}")
    return "\n".join(lines)


@tool
async def cached_web_search(query: str) -> str:
    """Search the web for current information. Results are cached to avoid
    repeated lookups of the same or similar queries."""
    return await cached_search(query)


async def cached_search(query: str) -> str:
    """The layered search itself, callable from other tools (e.g. news)."""
    settings = get_settings()
    redis = redis_client.get_redis()
    key = _cache_key(query)

    # Layer 1: Redis exact-match
    try:
        cached = await redis.get(key)
        if cached is not None:
            logger.info("web_search cache hit (exact): %s", query[:60])
            return _format(json.loads(cached))
    except Exception as e:
        logger.warning("web cache read failed: %s", e)

    # Layer 2: Qdrant semantic near-duplicate (fresh entries only)
    semantic = await _semantic_lookup(query)
    if semantic is not None:
        logger.info("web_search cache hit (semantic): %s", query[:60])
        return _format(semantic)

    # Layer 3: live Tavily
    results = await _run_tavily(query)

    # Only cache real results — caching empty/failed responses would freeze a
    # transient "no results" for the full TTL.
    if results:
        try:
            await redis.set(key, json.dumps(results), ex=settings.web_cache_ttl_seconds)
        except Exception as e:
            logger.warning("web cache write failed: %s", e)
        await _semantic_store(query, results)

    return _format(results)


async def _semantic_lookup(query: str) -> list[dict] | None:
    settings = get_settings()
    try:
        from src.rag.store import search_texts

        hits = await search_texts(
            settings.search_cache_collection,
            query,
            _CACHE_NS,
            limit=1,
            score_threshold=settings.web_cache_score_threshold,
        )
    except Exception as e:
        logger.warning("semantic cache lookup failed: %s", e)
        return None
    if not hits:
        return None
    hit = hits[0]
    ts = hit.get("ts", 0)
    if time.time() - ts > settings.web_cache_semantic_max_age_seconds:
        return None
    try:
        return json.loads(hit.get("results_json", "[]"))
    except Exception:
        return None


async def _semantic_store(query: str, results: list[dict]) -> None:
    try:
        from src.rag.store import upsert_texts

        await upsert_texts(
            get_settings().search_cache_collection,
            [query],
            [{"user_id": _CACHE_NS, "ts": time.time(), "results_json": json.dumps(results)}],
        )
    except Exception as e:
        logger.warning("semantic cache store failed: %s", e)
