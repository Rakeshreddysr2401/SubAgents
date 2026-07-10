"""Dependency probes shared by GET /system/preflight and scripts/preflight.py.

Each probe returns {"ok": bool, ...context...} with a short timeout and never
raises — the callers render, they don't handle exceptions.
"""

from __future__ import annotations

import os

PROBE_TIMEOUT_S = 2.0


async def llm_preflight() -> dict:
    """Is the configured chat endpoint reachable? (no generation — cheap)."""
    import httpx

    from src.configs.settings import get_settings
    from src.services.llm_registry import resolve_base_config

    s = get_settings()
    cfg = resolve_base_config(s)
    provider, base_url = cfg["provider"], cfg["base_url"]
    if provider in ("openai", "anthropic", "gemini") and not base_url:
        key_env = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }[provider]
        has_key = bool(cfg["api_key"] or os.getenv(key_env, ""))
        return {
            "ok": has_key,
            "provider": provider,
            "model": cfg["model"],
            "detail": "API key configured" if has_key
            else f"missing {key_env} (or LLM_API_KEY)",
        }
    probe_url = base_url.rstrip("/")
    if provider == "ollama":
        probe_url += "/api/tags"
    else:  # OpenAI-compatible (llama.cpp, vLLM, LM Studio)
        probe_url += "/models"
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
            r = await client.get(probe_url)
            r.raise_for_status()
        return {"ok": True, "provider": provider, "model": cfg["model"],
                "detail": f"reachable at {base_url}"}
    except Exception as e:
        return {"ok": False, "provider": provider, "model": cfg["model"],
                "detail": f"unreachable at {base_url}: {str(e)[:150]}"}


async def embeddings_preflight() -> dict:
    import httpx

    from src.configs.settings import get_settings

    s = get_settings()
    if s.embedding_provider == "openai":
        has_key = bool(os.getenv("OPENAI_API_KEY", ""))
        return {"ok": has_key, "provider": "openai", "model": s.embedding_model,
                "detail": "API key configured" if has_key else "missing OPENAI_API_KEY"}
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
            r = await client.get(f"{s.ollama_base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            models = [m.get("name", "") for m in r.json().get("models", [])]
        pulled = any(m.split(":")[0] == s.ollama_embedding_model.split(":")[0] for m in models)
        return {
            "ok": pulled,
            "provider": "ollama",
            "model": s.ollama_embedding_model,
            "detail": "model pulled" if pulled
            else f"run `ollama pull {s.ollama_embedding_model}` on {s.ollama_base_url}",
        }
    except Exception as e:
        return {"ok": False, "provider": "ollama", "model": s.ollama_embedding_model,
                "detail": f"Ollama unreachable at {s.ollama_base_url}: {str(e)[:150]}"}
