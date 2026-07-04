# Infrastructure

Hybrid deployment: **data services run in Docker**, the **app runs on the macOS
host** (so webcam, `say`, and `open -a` keep working). See `docker-compose.yml`.

## Services

| Service | Image | Port(s) | Volume | Purpose |
|---|---|---|---|---|
| postgres | `postgres:16-alpine` | 5432 | `pgdata` | LangGraph checkpoints (thread state) |
| redis | `redis:7-alpine` (AOF) | 6379 | `redisdata` | frame buffer, web cache, rate limits |
| qdrant | `qdrant/qdrant` | 6333 (HTTP), 6334 (gRPC) | `qdrantdata` | vector search (RAG + Mem0) |

All three declare healthchecks; `docker compose ps` shows `healthy` when ready.
Qdrant's dashboard is at <http://localhost:6333/dashboard>.

## Credentials & connection strings

Defaults (override in `.env`):

```
POSTGRES_DSN=postgresql://subagents:subagents@localhost:5432/subagents
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333
```

The Postgres user/password/db are set in `docker-compose.yml`
(`subagents`/`subagents`/`subagents`). Change these for any non-local deployment.

## Data lifecycle & backup

- **Postgres** — checkpoint tables are created automatically on startup
  (`AsyncPostgresSaver.setup()`). Back up with `pg_dump`. The open-source
  checkpointer has no TTL; prune old threads yourself if needed.
- **Redis** — AOF persistence is on; keys are ephemeral by design (frames
  expire via TTL, caches via TTL, rate-limit buckets after 60s).
- **Qdrant** — collections live in the `qdrantdata` volume. Back up by snapshotting
  the volume or via Qdrant's snapshot API.

## Resetting state

```bash
docker compose down -v      # ⚠️ deletes all volumes (checkpoints, vectors, cache)
docker compose up -d
```

Re-creating collections happens automatically on next app startup
(`ensure_collections`). Mem0 re-creates `mem0_memories` on first use.

## Startup resilience

The app boots even when optional services are degraded:

- Swiggy MCP unreachable → food tools disabled, warning logged.
- Mem0 init fails → long-term memory disabled, graph still runs.
- Qdrant collection setup fails → RAG degraded, warning logged.

Postgres is the one hard dependency (it holds conversation state).
