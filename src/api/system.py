"""System health/observability endpoints.

GET /health            unauth liveness probe (static — never blocks on deps)
GET /status            auth'd: real dependency + provider health snapshot
GET /metrics           Prometheus text, bearer METRICS_TOKEN (Prometheus can't
                       do the cookie dance; 404 when no token is configured)
GET /system/preflight  auth'd: first-run diagnostics for the setup wizard —
                       is the LLM reachable, are embedding models pulled, is
                       the Swiggy login live, is the frontend built.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.auth import get_user_id
from src.configs.settings import get_settings
from src.services import llm_registry, mcp_providers, metrics

router = APIRouter()

_PROBE_TIMEOUT_S = 2.0
_WEB_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist"

_metrics_bearer = HTTPBearer(auto_error=False)


@router.get("/health")
async def health():
    return {"status": "ok", "service": "subagents"}


async def _probe(coro) -> dict:
    """Run a dependency probe with a short timeout; never raise."""
    try:
        async with asyncio.timeout(_PROBE_TIMEOUT_S):
            await coro
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def _postgres_probe(request: Request) -> dict:
    async def _ping():
        async with request.app.state.db.connection() as conn:
            await conn.execute("SELECT 1")

    return await _probe(_ping())


async def _redis_probe(request: Request) -> dict:
    return await _probe(request.app.state.redis.ping())


async def _qdrant_probe(request: Request) -> dict:
    return await _probe(request.app.state.qdrant.get_collections())


@router.get("/status")
async def status(request: Request, user_id: str = Depends(get_user_id)):
    postgres, redis, qdrant = await asyncio.gather(
        _postgres_probe(request), _redis_probe(request), _qdrant_probe(request)
    )
    return {
        "llm": llm_registry.status(),
        "mcp": mcp_providers.status(),
        "postgres": postgres,
        "redis": redis,
        "qdrant": qdrant,
        "mem0": request.app.state.mem0 is not None,
        "metrics": metrics.snapshot(),
    }


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics(
    credentials: HTTPAuthorizationCredentials = Depends(_metrics_bearer),
):
    token = get_settings().metrics_token
    if not token:
        raise HTTPException(status_code=404, detail="Metrics not enabled")
    if credentials is None or credentials.credentials != token:
        raise HTTPException(status_code=401, detail="Invalid metrics token")
    return render_metrics()


def render_metrics() -> str:
    # Fold the LLM health gauge in lazily so it's correct even if no
    # report_* call has fired yet this process.
    metrics.set_gauge("llm_primary_up", 1 if llm_registry.primary_available() else 0)
    return metrics.render_prometheus()


async def _llm_preflight() -> dict:
    """Is the configured chat endpoint reachable? (no generation — cheap)."""
    import httpx

    from src.configs.llm import resolve_base_config

    s = get_settings()
    cfg = resolve_base_config(s)
    provider, base_url = cfg["provider"], cfg["base_url"]
    if provider in ("openai", "anthropic", "gemini") and not base_url:
        import os

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
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            r = await client.get(probe_url)
            r.raise_for_status()
        return {"ok": True, "provider": provider, "model": cfg["model"],
                "detail": f"reachable at {base_url}"}
    except Exception as e:
        return {"ok": False, "provider": provider, "model": cfg["model"],
                "detail": f"unreachable at {base_url}: {str(e)[:150]}"}


async def _embeddings_preflight() -> dict:
    import httpx

    s = get_settings()
    if s.embedding_provider == "openai":
        import os

        has_key = bool(os.getenv("OPENAI_API_KEY", ""))
        return {"ok": has_key, "provider": "openai", "model": s.embedding_model,
                "detail": "API key configured" if has_key else "missing OPENAI_API_KEY"}
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
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


@router.get("/system/preflight")
async def preflight(request: Request, user_id: str = Depends(get_user_id)):
    postgres, redis, qdrant, llm, embeddings = await asyncio.gather(
        _postgres_probe(request),
        _redis_probe(request),
        _qdrant_probe(request),
        _llm_preflight(),
        _embeddings_preflight(),
    )
    mcp_status = mcp_providers.status()
    swiggy = mcp_status["tokens"].get("swiggy", {})
    checks = {
        "postgres": postgres,
        "redis": redis,
        "qdrant": qdrant,
        "llm": llm,
        "embeddings": embeddings,
        "swiggy": {
            # Optional integration: "ok" here means "not in a broken state" —
            # absent is fine, expired/stale is what needs the user's attention.
            "ok": not swiggy.get("stale", False),
            "configured": swiggy.get("source", "none") != "none",
            "days_left": swiggy.get("days_left"),
            "detail": "run `uv run python scripts/swiggy_login.py` to enable ordering"
            if swiggy.get("source", "none") == "none" else "",
        },
        "frontend": {
            "ok": (_WEB_DIST_DIR / "index.html").exists(),
            "detail": "" if (_WEB_DIST_DIR / "index.html").exists()
            else "run `npm install && npm run build` in web/",
        },
    }
    required = ("postgres", "redis", "qdrant", "llm", "embeddings", "frontend")
    return {"ready": all(checks[k]["ok"] for k in required), "checks": checks}
