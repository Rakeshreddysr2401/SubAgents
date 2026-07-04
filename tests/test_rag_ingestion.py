"""RAG ingestion + retrieval against an in-memory Qdrant with a fake embedder."""

import pytest
from qdrant_client import AsyncQdrantClient


class FakeEmbeddings:
    """Deterministic bag-of-words hashing embedder (dim=32) — no network."""

    DIM = 32

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.DIM
        for tok in text.lower().split():
            v[hash(tok) % self.DIM] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture
async def rag_env(monkeypatch):
    client = AsyncQdrantClient(":memory:")
    from qdrant_client.models import Distance, VectorParams

    for coll in ("documents", "history", "search_cache"):
        await client.create_collection(
            coll, vectors_config=VectorParams(size=FakeEmbeddings.DIM, distance=Distance.COSINE)
        )

    import src.rag.qdrant as qmod
    import src.rag.store as store
    import src.rag.embeddings as emb

    monkeypatch.setattr(qmod, "get_qdrant", lambda: client)
    monkeypatch.setattr(store, "get_qdrant", lambda: client)
    monkeypatch.setattr(store, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(emb, "get_embeddings", lambda: FakeEmbeddings())
    yield client
    await client.close()


async def test_ingest_and_search_documents(rag_env):
    from src.rag.ingestion import ingest_document

    text = b"The mitochondria is the powerhouse of the cell. Photosynthesis occurs in chloroplasts."
    result = await ingest_document("alice", "biology.txt", text)
    assert result["chunks"] >= 1
    assert result["filename"] == "biology.txt"

    from src.rag.store import search_texts

    hits = await search_texts("documents", "powerhouse of the cell", "alice", limit=3)
    assert hits
    assert any("mitochondria" in h["text"] for h in hits)


async def test_search_is_user_scoped(rag_env):
    from src.rag.ingestion import ingest_document
    from src.rag.store import search_texts

    await ingest_document("alice", "a.txt", b"alice secret pancake recipe")
    await ingest_document("bob", "b.txt", b"bob secret waffle recipe")

    alice_hits = await search_texts("documents", "secret recipe", "alice", limit=5)
    assert alice_hits
    assert all(h["user_id"] == "alice" for h in alice_hits)
    assert not any("waffle" in h["text"] for h in alice_hits)


async def test_empty_document(rag_env):
    from src.rag.ingestion import ingest_document

    result = await ingest_document("alice", "empty.txt", b"   ")
    assert result["chunks"] == 0
    assert result["doc_id"] is None
