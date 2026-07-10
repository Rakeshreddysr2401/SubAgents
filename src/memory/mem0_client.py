"""Mem0 long-term memory client (self-hosted, Qdrant-backed).

Mem0 uses an LLM internally to extract durable facts from conversation. That
LLM is configured independently of the chat model: MEM0_LLM_PROVIDER defaults
to "main" (follow the chat provider — zero-key local installs work out of the
box), but fact extraction produces noticeably better JSON on OpenAI — set
MEM0_LLM_PROVIDER=openai to upgrade when a key is available.
"""

from mem0 import AsyncMemory

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.rag.embeddings import mem0_embedder_config

logger = get_logger(__name__)


def _mem0_llm_config() -> dict:
    s = get_settings()
    provider = s.mem0_llm_provider
    if provider == "main":
        # Follow the chat model's provider; cloud chat keeps cloud extraction.
        provider = {
            "llama_cpp": "llama_cpp",
            "ollama": "ollama",
            "openai": "openai",
            "anthropic": "anthropic",
            "gemini": "gemini",
        }[s.llm_provider]
    if provider == "llama_cpp":
        return {
            "provider": "openai",  # OpenAI-compatible endpoint
            "config": {
                "model": s.llm_model or s.model_name,
                "openai_base_url": s.llm_base_url or s.llama_cpp_base_url,
                "api_key": "not-needed",
            },
        }
    if provider == "ollama":
        return {
            "provider": "ollama",
            "config": {
                "model": s.llm_model or s.model_name,
                "ollama_base_url": s.ollama_base_url,
            },
        }
    if provider in ("anthropic", "gemini"):
        # mem0 has native providers for both; API keys come from the standard
        # env vars (ANTHROPIC_API_KEY / GOOGLE_API_KEY).
        return {"provider": provider, "config": {"model": s.llm_model}} if s.llm_model else {
            "provider": provider, "config": {}
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
