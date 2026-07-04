"""Thin async helpers for embedding + upsert/search against Qdrant collections.

Uses the shared AsyncQdrantClient and the configured embeddings provider.
Kept deliberately small so tests can run against AsyncQdrantClient(":memory:").
"""

import uuid

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
)

from src.rag.embeddings import get_embeddings
from src.rag.qdrant import get_qdrant


async def _embed(texts: list[str]) -> list[list[float]]:
    # LangChain embeddings are sync; run off the loop to avoid blocking.
    import asyncio

    return await asyncio.to_thread(get_embeddings().embed_documents, texts)


async def _embed_one(text: str) -> list[float]:
    import asyncio

    return await asyncio.to_thread(get_embeddings().embed_query, text)


async def upsert_texts(
    collection: str, texts: list[str], payloads: list[dict]
) -> list[str]:
    """Embed and upsert texts with matching payloads. Returns point ids."""
    if not texts:
        return []
    vectors = await _embed(texts)
    ids = [str(uuid.uuid4()) for _ in texts]
    points = [
        PointStruct(id=pid, vector=vec, payload={**payload, "text": text})
        for pid, vec, text, payload in zip(ids, vectors, texts, payloads)
    ]
    await get_qdrant().upsert(collection_name=collection, points=points)
    return ids


def _user_filter(user_id: str, extra: dict | None = None) -> Filter:
    conditions = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
    for key, value in (extra or {}).items():
        conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions)


async def search_texts(
    collection: str,
    query: str,
    user_id: str,
    limit: int = 5,
    extra_filter: dict | None = None,
    score_threshold: float | None = None,
) -> list[dict]:
    """Semantic search scoped to a user. Returns [{score, payload...}]."""
    vector = await _embed_one(query)
    results = await get_qdrant().query_points(
        collection_name=collection,
        query=vector,
        query_filter=_user_filter(user_id, extra_filter),
        limit=limit,
        score_threshold=score_threshold,
        with_payload=True,
    )
    return [{"score": p.score, **(p.payload or {})} for p in results.points]
