"""Chat-model builder + primary-LLM health state.

build_chat_model(cfg) turns a plain config dict into a LangChain chat model
for any supported provider:

    llama_cpp | openai   → ChatOpenAI (any OpenAI-compatible server; a
                           non-negative `slot` is forwarded as llama.cpp's
                           `id_slot` so each agent keeps its own KV-cache
                           slot on a `--parallel N` server)
    anthropic            → ChatAnthropic
    gemini               → ChatGoogleGenerativeAI
    ollama               → ChatOllama

Cloud SDKs are imported lazily so only the providers actually used need
their package importable at runtime.

Primary-health state (drives ResilientModelMiddleware's routing): after a
connection-class failure the primary is marked down for PRIMARY_COOLDOWN_S
and calls go straight to the configured fallback until the window expires,
then the primary is re-probed. `is_connection_error` separates "server
unreachable/dead" (retry elsewhere) from request-shaped errors (a fallback
would fail the same way).
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

PRIMARY_COOLDOWN_S = 60.0

_health_lock = threading.Lock()
_primary_down_until: float = 0.0
_fallback_used_total: int = 0


def build_chat_model(cfg: dict):
    """Build a chat model from a config dict.

    Keys: provider, model, base_url, api_key, max_tokens, slot, temperature.
    Missing keys get safe defaults; falsy api_key is omitted so provider SDKs
    fall back to their own env vars (OPENAI_API_KEY, ANTHROPIC_API_KEY, …).
    """
    provider = cfg.get("provider", "llama_cpp")
    model = cfg.get("model", "default")
    base_url = cfg.get("base_url", "")
    api_key = cfg.get("api_key", "")
    max_tokens = cfg.get("max_tokens")
    slot = cfg.get("slot")
    temperature = cfg.get("temperature", 0)

    if provider in ("llama_cpp", "openai"):
        from langchain_openai import ChatOpenAI

        kwargs: dict = {
            "model": model,
            "temperature": temperature,
            # Retry policy lives in ResilientModelMiddleware (one visible
            # retry, then the cooldown + fallback ladder). The SDK's hidden
            # default of 2 more internal retries stacked on top would make a
            # dead primary cost ~6 connect attempts before the degraded
            # reply instead of ~2.
            "max_retries": 0,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        # Pin a llama.cpp KV-cache slot for this agent (server needs
        # --parallel N). Forwarded verbatim into the request body.
        if slot is not None and slot >= 0:
            kwargs["extra_body"] = {"id_slot": slot}
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=api_key or None,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key or None,
            temperature=temperature,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model,
            base_url=base_url or "http://localhost:11434",
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown LLM provider: {provider!r}. "
        "Choose from: llama_cpp | openai | anthropic | gemini | ollama"
    )


# ── Primary health tracking ─────────────────────────────────────────────────

def primary_available() -> bool:
    """False while the primary is inside its post-failure cooldown window."""
    with _health_lock:
        return time.monotonic() >= _primary_down_until


def report_primary_failure() -> None:
    """Mark the primary down for PRIMARY_COOLDOWN_S (connection errors only)."""
    from src.services import metrics

    global _primary_down_until
    with _health_lock:
        _primary_down_until = time.monotonic() + PRIMARY_COOLDOWN_S
    metrics.inc("llm_primary_failures_total")
    metrics.set_gauge("llm_primary_up", 0)
    logger.warning("Primary LLM marked down for %.0fs", PRIMARY_COOLDOWN_S)


def report_primary_success() -> None:
    from src.services import metrics

    global _primary_down_until
    with _health_lock:
        _primary_down_until = 0.0
    metrics.set_gauge("llm_primary_up", 1)


def report_fallback_used() -> None:
    from src.services import metrics

    global _fallback_used_total
    with _health_lock:
        _fallback_used_total += 1
    metrics.inc("llm_fallback_used_total")


def reset_health() -> None:
    """Test seam: clear cooldown + counters."""
    global _primary_down_until, _fallback_used_total
    with _health_lock:
        _primary_down_until = 0.0
        _fallback_used_total = 0


def is_connection_error(exc: BaseException) -> bool:
    """Heuristic: does this exception mean "server unreachable / dead", as
    opposed to a request-shaped error the fallback would hit too?"""
    names = {t.__name__ for t in type(exc).__mro__}
    wanted = {
        "APIConnectionError", "APITimeoutError", "InternalServerError",
        "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout",
        "PoolTimeout", "TimeoutException", "ConnectionError", "OSError",
    }
    if names & wanted:
        return True
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        return is_connection_error(cause)
    return False


def status() -> dict:
    """Health-API view of the LLM layer (never contains keys/secrets)."""
    from src.configs.llm import resolve_base_config
    from src.configs.settings import get_settings

    s = get_settings()
    cfg = resolve_base_config(s)
    with _health_lock:
        down_for = max(0.0, _primary_down_until - time.monotonic())
        fallback_used = _fallback_used_total
    fallback = None
    if s.fallback_llm_provider and s.fallback_llm_model:
        fallback = f"{s.fallback_llm_provider}/{s.fallback_llm_model}"
    return {
        "provider": cfg["provider"],
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "primary_available": down_for == 0.0,
        "primary_retry_in_s": round(down_for, 1),
        "fallback": fallback,
        "fallback_used_total": fallback_used,
        "slots": s.llm_slots if cfg["provider"] == "llama_cpp" else None,
    }
