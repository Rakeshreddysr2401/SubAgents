"""Embeddings provider switch (OpenAI or Ollama) for RAG and Mem0.

The chosen provider fixes the vector dimension for every Qdrant collection and
for Mem0. Switching providers requires re-creating collections — see
docs/memory-and-rag.md.
"""

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from src.configs.settings import get_settings


@lru_cache
def get_embeddings() -> Embeddings:
    s = get_settings()
    if s.embedding_provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(model=s.ollama_embedding_model, base_url=s.ollama_base_url)
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=s.openai_embedding_model)


def mem0_embedder_config() -> dict:
    """Embedder block for Mem0's from_config()."""
    s = get_settings()
    if s.embedding_provider == "ollama":
        return {
            "provider": "ollama",
            "config": {
                "model": s.ollama_embedding_model,
                "ollama_base_url": s.ollama_base_url,
                "embedding_dims": s.embedding_dim,
            },
        }
    return {
        "provider": "openai",
        "config": {"model": s.openai_embedding_model, "embedding_dims": s.embedding_dim},
    }
