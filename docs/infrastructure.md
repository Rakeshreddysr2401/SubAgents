# Infrastructure

Hybrid deployment: **data services run in Docker**, the **app runs on the macOS
host** (so webcam, `say`, and `open -a` keep working). See `docker-compose.yml`.

## Services

| Service | Image | Port(s) | Volume | Purpose |
|---|---|---|---|---|
| postgres | `postgres:16-alpine` | 5432 | `pgdata` | LangGraph checkpoints + `users`/`chat_threads` |
| redis | `redis:7-alpine` (AOF) | 6379 | `redisdata` | frame buffer, web cache, rate limits, refresh-token sessions |
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
  (`AsyncPostgresSaver.setup()`); the `users` and `chat_threads` tables are
  created the same way, idempotently, via `src/services/db.py::ensure_schema()`.
  Back up all of it with `pg_dump` — `users`/`chat_threads` are the durable
  account/session data, not just cache. The open-source checkpointer has no
  TTL; prune old threads yourself if needed. Deleting a user cascades to their
  `chat_threads` rows (`ON DELETE CASCADE`) but leaves the underlying
  checkpoint rows in place (orphaned, harmless).
- **Redis** — AOF persistence is on; keys are ephemeral by design (frames
  expire via TTL, caches via TTL, rate-limit buckets after 60s, refresh-token
  sessions after `REFRESH_TOKEN_TTL_DAYS`). Losing Redis mid-session forces
  every logged-in user to sign in again — Postgres remains the source of truth
  for accounts and conversations.
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
