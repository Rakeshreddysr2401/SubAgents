"""Mem0 long-term memory client (self-hosted, Qdrant-backed).

Mem0 uses an LLM internally to extract durable facts from conversation. That
LLM is configured independently of the chat model (MEM0_LLM_PROVIDER) because
fact extraction needs reliable JSON — keep it on OpenAI even when the chat
model is a local llama.cpp/Ollama server.
"""

from mem0 import AsyncMemory

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.rag.embeddings import mem0_embedder_config

logger = get_logger(__name__)


def _mem0_llm_config() -> dict:
    s = get_settings()
    if s.mem0_llm_provider == "llama_cpp":
        return {
            "provider": "openai",  # OpenAI-compatible endpoint
            "config": {
                "model": s.model_name,
                "openai_base_url": s.llama_cpp_base_url,
                "api_key": "not-needed",
            },
        }
    return {"provider": "openai", "config": {"model": s.mem0_llm_model}}


def build_mem0_config() -> dict:
    s = get_settings()
    # qdrant_url like http://localhost:6333 → split host/port for Mem0
    from urllib.parse import urlparse

    parsed = urlparse(s.qdrant_url)
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": s.mem0_collection,
                "host": parsed.hostname or "localhost",
                "port": parsed.port or 6333,
                "embedding_model_dims": s.embedding_dim,
            },
        },
        "embedder": mem0_embedder_config(),
        "llm": _mem0_llm_config(),
    }


async def make_mem0() -> AsyncMemory:
    # from_config is synchronous in mem0 2.x; run it off the event loop since
    # it may touch the network (vector store / embedder handshakes).
    import asyncio

    return await asyncio.to_thread(AsyncMemory.from_config, build_mem0_config())
