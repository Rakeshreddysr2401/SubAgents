#!/usr/bin/env python3
"""First-run preflight: verify every dependency before starting the server.

  uv run python scripts/preflight.py

Checks Postgres/Redis/Qdrant (docker compose up -d), the configured LLM
endpoint, the embedding model, the Swiggy token, and the built frontend.
Exit code 0 = ready to run `uv run uvicorn main:app --port 2024`.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.configs.settings import get_settings  # noqa: E402

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def _line(name: str, ok: bool, detail: str, required: bool = True) -> None:
    if ok:
        mark = f"{GREEN}✓{RESET}"
    elif required:
        mark = f"{RED}✗{RESET}"
    else:
        mark = f"{YELLOW}–{RESET}"
    print(f"  {mark} {name:<12} {detail}")


async def main() -> int:
    s = get_settings()
    print("SubAgents preflight\n")
    failures = 0

    # Postgres
    try:
        import psycopg

        async with await asyncio.wait_for(
            psycopg.AsyncConnection.connect(s.postgres_dsn), timeout=3
        ) as conn:
            await conn.execute("SELECT 1")
        _line("postgres", True, s.postgres_dsn.split("@")[-1])
    except Exception as e:
        _line("postgres", False, f"{e} — run `docker compose up -d`")
        failures += 1

    # Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(s.redis_url)
        await asyncio.wait_for(r.ping(), timeout=3)
        await r.aclose()
        _line("redis", True, s.redis_url)
    except Exception as e:
        _line("redis", False, f"{e} — run `docker compose up -d`")
        failures += 1

    # Qdrant
    try:
        from qdrant_client import AsyncQdrantClient

        qc = AsyncQdrantClient(url=s.qdrant_url)
        await asyncio.wait_for(qc.get_collections(), timeout=3)
        await qc.close()
        _line("qdrant", True, s.qdrant_url)
    except Exception as e:
        _line("qdrant", False, f"{e} — run `docker compose up -d`")
        failures += 1

    # LLM + embeddings reuse the same probes as GET /system/preflight.
    from src.services.preflight import embeddings_preflight, llm_preflight

    llm = await llm_preflight()
    _line("llm", llm["ok"], f"{llm['provider']}/{llm['model']}: {llm['detail']}")
    failures += 0 if llm["ok"] else 1

    emb = await embeddings_preflight()
    _line("embeddings", emb["ok"], f"{emb['provider']}/{emb['model']}: {emb['detail']}")
    failures += 0 if emb["ok"] else 1

    # Swiggy (optional)
    from src.services import mcp_providers

    swiggy = mcp_providers.status()["tokens"].get("swiggy", {})
    configured = swiggy.get("source", "none") != "none"
    days = swiggy.get("days_left")
    _line(
        "swiggy", configured,
        f"token from {swiggy.get('source')}, {days} days left" if configured
        else "not configured (optional) — uv run python scripts/swiggy_login.py",
        required=False,
    )

    # Frontend build
    dist = Path(__file__).resolve().parent.parent / "web" / "dist" / "index.html"
    _line("frontend", dist.exists(),
          "web/dist ready" if dist.exists() else "run `npm install && npm run build` in web/")
    failures += 0 if dist.exists() else 1

    print()
    if failures:
        print(f"{RED}{failures} required check(s) failed.{RESET}")
        return 1
    print(f"{GREEN}Ready.{RESET} Start with: uv run uvicorn main:app --port 2024")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
