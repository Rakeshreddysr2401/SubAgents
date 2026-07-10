"""LLM factories.

get_llm(agent)     — main chat/agent model. Provider comes from settings
                     (llama_cpp | openai | anthropic | gemini | ollama).
                     Passing the agent name pins that agent's llama.cpp
                     KV-cache slot (LLM_SLOTS) and applies any per-agent
                     override (AGENT_LLM_OVERRIDES).
get_utility_llm()  — small/cheap model for background work: turn summaries,
                     frame descriptions, Mem0-style extraction.
get_vision_llm()   — the multimodal model for image analysis (guardian mode).
                     Defaults to the dedicated VISION_LLM_* endpoint so vision
                     keeps working even when the chat model is text-only.
get_fallback_llm() — the configured cloud fallback (FALLBACK_LLM_*), or None.
                     Used by ResilientModelMiddleware while the primary is in
                     its post-failure cooldown window.

All construction goes through src/services/llm_registry.build_chat_model();
these functions only resolve settings into a config dict. Dependencies flow
one way: configs/llm → services/llm_registry (never back).
"""

from src.configs.settings import get_settings
from src.services.llm_registry import build_chat_model, resolve_base_config

__all__ = [
    "get_llm", "get_utility_llm", "get_vision_llm", "get_fallback_llm",
    "resolve_base_config",  # re-exported from llm_registry (canonical home)
]


def get_llm(agent: str | None = None, temperature: float = 0):
    """A fresh chat model for `agent` (or the global default).

    llama.cpp slot pinning applies only to the llama_cpp provider — a cloud
    API has no KV slots, and Ollama manages its own cache.
    """
    s = get_settings()
    cfg = resolve_base_config(s)
    if agent and cfg["provider"] == "llama_cpp":
        slot = s.llm_slots.get(agent)
        if slot is not None:
            cfg["slot"] = slot
    if agent:
        override = s.agent_llm_overrides.get(agent)
        if override:
            cfg.update({k: v for k, v in override.items() if v is not None})
    cfg["temperature"] = temperature
    return build_chat_model(cfg)


def get_utility_llm(temperature: float = 0):
    s = get_settings()
    cfg = resolve_base_config(s)
    if cfg["provider"] == "openai":
        cfg["model"] = s.utility_model
    cfg["temperature"] = temperature
    return build_chat_model(cfg)


def get_vision_llm(temperature: float = 0):
    s = get_settings()
    if s.vision_llm_provider and s.vision_llm_provider != "llama_cpp":
        # Explicit vision provider (cloud VLM, Ollama VLM, …).
        cfg = resolve_base_config(s)
        cfg["provider"] = s.vision_llm_provider
        if s.vision_llm_base_url:
            cfg["base_url"] = s.vision_llm_base_url
        if s.vision_model:
            cfg["model"] = s.vision_model
        cfg["temperature"] = temperature
        return build_chat_model(cfg)
    if s.llm_provider in ("openai", "anthropic", "gemini") and not s.vision_llm_base_url:
        # Full-cloud stack with no dedicated VLM configured — the main cloud
        # model is multimodal anyway.
        cfg = resolve_base_config(s)
        cfg["temperature"] = temperature
        return build_chat_model(cfg)
    # OpenAI-compatible VLM endpoint (llama.cpp on the LAN by default).
    return build_chat_model({
        "provider": "llama_cpp",
        "base_url": s.vision_llm_base_url or s.llama_cpp_base_url,
        "api_key": "not-needed",
        "model": s.vision_model or s.model_name,
        "temperature": temperature,
    })


def get_fallback_llm():
    """The configured cloud fallback model, or None. Fresh instance per call.

    No slot pin (cloud servers have no KV slots) and no per-agent overrides —
    one fallback model serves every agent.
    """
    s = get_settings()
    if not (s.fallback_llm_provider and s.fallback_llm_model):
        return None
    return build_chat_model({
        "provider": "llama_cpp" if s.fallback_llm_provider == "llamacpp" else s.fallback_llm_provider,
        "model": s.fallback_llm_model,
        "base_url": s.fallback_llm_base_url,
        "api_key": s.fallback_llm_api_key,
        "max_tokens": s.llm_max_tokens,
    })
