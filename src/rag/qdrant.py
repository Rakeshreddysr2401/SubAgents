"""Qdrant client + collection lifecycle.

Collections (all cosine, dim = settings.embedding_dim). Names are suffixed
with the embedding dimension (documents_768, …) so switching embedding
providers is non-destructive — each dim gets its own collections and the old
ones are simply orphaned (list/clean them with scripts/migrate_qdrant.py):
  documents_<dim>     — user-uploaded document chunks
  history_<dim>       — conversation turn summaries + vision-frame descriptions
  search_cache_<dim>  — semantic web-search cache
  (mem0_memories_<dim> is created and managed by Mem0 itself)

ensure_collections() creates missing collections and fails fast if an existing
one has a different vector size than the configured embedding provider (only
possible via an EMBEDDING_DIM override change, but cheap to keep checking).
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
                    f"'{s.embedding_provider}' embedder produces {dim}. Drop it with "
                    f"`uv run python scripts/migrate_qdrant.py --drop {name}` and restart."
                )
        else:
            await client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s' (dim=%d)", name, dim)
