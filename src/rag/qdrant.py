"""Qdrant client + collection lifecycle.

Collections (all cosine, dim = settings.embedding_dim):
  documents      — user-uploaded document chunks
  history        — conversation turn summaries + vision-frame descriptions
  search_cache   — semantic web-search cache
  (mem0_memories is created and managed by Mem0 itself)

ensure_collections() creates missing collections and fails fast if an existing
one has a different vector size than the configured embedding provider.
"""

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings

logger = get_logger(__name__)

_client: AsyncQdrantClient | None = None


def get_qdrant() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=get_settings().qdrant_url)
    return _client


def set_qdrant(client: AsyncQdrantClient) -> None:
    """Allow the app lifespan (or tests) to inject a shared/in-memory client."""
    global _client
    _client = client


def rag_collections() -> list[str]:
    s = get_settings()
    return [s.documents_collection, s.history_collection, s.search_cache_collection]


async def ensure_collections(client: AsyncQdrantClient | None = None) -> None:
    s = get_settings()
    client = client or get_qdrant()
    dim = s.embedding_dim

    for name in rag_collections():
        if await client.collection_exists(name):
            info = await client.get_collection(name)
            existing = info.config.params.vectors.size
            if existing != dim:
                raise RuntimeError(
                    f"Qdrant collection '{name}' has vector size {existing} but the "
                    f"'{s.embedding_provider}' embedder produces {dim}. Drop and "
                    f"re-create the collection (see docs/memory-and-rag.md)."
                )
        else:
            await client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d)", name, dim)
