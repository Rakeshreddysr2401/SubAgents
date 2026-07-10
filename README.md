# SubAgents — Your Private, Multi-Agent AI Assistant for the Mac

A locally-run, multimodal AI assistant you own end-to-end. It runs on your Mac,
talks to **your** model server (e.g. a Mac mini running llama.cpp — no cloud
key required) or to cloud providers (OpenAI / Anthropic / Gemini) when you
choose, and keeps every conversation, memory, and camera frame on your own
hardware.

Built on **LangGraph** (swarm orchestration), **`deepagents`** (planning),
**FastAPI** (streaming runtime), a **React** SPA with light/dark theming, and a
durable memory stack: **PostgreSQL** (checkpoints), **Redis** (frames & caches),
**Qdrant** (vectors), **Mem0** (long-term memory).

---

## What it does

- **Six specialist agents, one conversation** — `conversation` (default router),
  `swiggy` (restaurant food ordering), `instamart` (groceries), `dineout`
  (table reservations), `tracker` (deliveries), and `planner` (a real
  `deepagents` deep agent that decomposes multi-step requests, with a
  `research` subagent for web/document research). Guarded `transfer_to_*`
  handoffs with sticky routing and loop protection.
- **Order food, groceries, and tables with your own Swiggy account** — official
  Swiggy MCP servers, OAuth 2.1 PKCE login (`scripts/swiggy_login.py`), hot
  token reload without restarts, and graceful degradation when a login expires.
  **Order placement always pauses for your approval** (human-in-the-loop).
- **Your model, your rules** — point `LLAMA_CPP_BASE_URL` at any
  OpenAI-compatible server. Per-agent llama.cpp KV-cache **slot pinning**
  (`--parallel 4`) keeps every agent's prompt prefix hot. Optional **cloud
  fallback** takes over automatically (with a cooldown) if your server goes
  down — and the assistant *says so* instead of erroring.
- **Fully local by default** — embeddings (Ollama `nomic-embed-text`) and Mem0
  fact extraction follow your local provider; an OpenAI key is an optional
  quality upgrade, never a requirement.
- **Long-thread durability** — conversations are summarized in place when they
  outgrow a small local context window; nothing falls off a cliff.
- **Time travel** — hover any of your past messages and *edit & resend from
  here*: the thread forks from that exact checkpoint (LangGraph-native).
- **Live visibility** — real token streaming plus live agent badges, tool
  call/result cards, long-tool progress lines, and a plan tracker for the
  planner's todo list.
- **Sees, speaks, listens** — webcam vision (`capture_webcam`), guardian mode
  ("watch my room" → camera monitoring with alerts), browser TTS for replies
  and reminders, wake-word + speech input.
- **Everything an assistant needs** — Postgres-backed reminders that speak up,
  a per-user shopping list the grocery agent consults, internet radio, news
  summaries, location-aware answers, document upload + RAG, cached web search.
- **Production posture** — real signup/login (httpOnly-cookie JWT sessions,
  rotating refresh tokens, auto-generated JWT secret), per-user rate limits,
  `/status` health API, Prometheus `/metrics`, a first-run **setup wizard**
  that diagnoses your install, and a launchd unit for run-at-login.

---

## Quickstart

```bash
docker compose up -d                    # Postgres, Redis, Qdrant
uv sync                                 # backend dependencies
cp .env.example .env                    # point LLM at your server (see below)
cd web && npm install && npm run build && cd ..   # build the UI once

uv run python scripts/preflight.py      # verifies everything before first run
uv run uvicorn main:app --port 2024
```

Open <http://localhost:2024>. If anything is missing, the app lands on the
**setup wizard** (`/setup`) which tells you exactly what to fix. With
`AUTH_DISABLED=true` (the dev default) you go straight to chat; set it to
`false` for real accounts.

**Your LLM server** — any OpenAI-compatible endpoint works. The recommended
setup is llama.cpp on a separate Mac (mini) on your LAN:

```bash
# on the model server
llama-server -m your-model.gguf --host 0.0.0.0 --port 8080 --parallel 4 --jinja
```

```bash
# in .env
LLM_PROVIDER=llama_cpp
LLAMA_CPP_BASE_URL=http://your-mini.local:8080/v1
SUPERVISOR_MODEL=your-model-name
# LLM_SLOTS pins one KV-cache slot per agent — matches --parallel 4
```

Cloud instead (or as fallback): `LLM_PROVIDER=openai|anthropic|gemini` + the
provider's API key, and/or `FALLBACK_LLM_*` to arm automatic failover. Full
options: **[docs/providers.md](docs/providers.md)**. Swiggy ordering:
**[docs/mcp.md](docs/mcp.md)**. Auto-start at login:
`./scripts/install_launchd.sh`.

> **Security note**: a Swiggy OAuth token file was committed to this repo's
> history before v0.8 and has been removed from the tree; the old token must be
> treated as leaked — re-run the Swiggy login to rotate it. Token files are
> gitignored now.

---

## Architecture at a glance

```
React SPA (web/) ── POST /chat (SSE) · POST /chat/resume · WS /ws/frames
                  ── GET /events · POST /upload · GET /status · GET /system/preflight
                  ── /auth/* · /threads/* (incl. /checkpoints for time travel)
   ▼
FastAPI (host, :2024)   main.py → src/app.py   [lifespan owns all resources;
                                                serves web/dist/ for the SPA routes]
   ▼
Parent graph:  START → recall_memories (Mem0) → swarm → END
   swarm:  conversation (default) ⇄ swiggy ⇄ instamart ⇄ dineout ⇄ tracker ⇄ planner
           guarded handoffs · HITL interrupt() on gated tools · per-agent
           summarization · ResilientModelMiddleware (cooldown → fallback)
   ▼
Post-turn background:  Mem0 write · turn summary → Qdrant · frame → Qdrant
```

Full details in **[docs/architecture.md](docs/architecture.md)**.

---

## Documentation

| Doc | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Graph, turn lifecycle, handoffs, state, stores |
| [docs/setup.md](docs/setup.md) | Prerequisites, install, providers, running, tests |
| [docs/providers.md](docs/providers.md) | LLM providers, slot pinning, cloud fallback |
| [docs/mcp.md](docs/mcp.md) | Swiggy MCP login, tokens, staleness, re-arm |
| [docs/infrastructure.md](docs/infrastructure.md) | Containers, volumes, backup, resilience |
| [docs/memory-and-rag.md](docs/memory-and-rag.md) | Mem0, RAG collections, dim-suffixed collections |
| [docs/api.md](docs/api.md) | Endpoint + SSE contract reference |
| [CLAUDE.md](CLAUDE.md) | Developer/AI implementation reference |

---

## Project layout

```
main.py                  # uvicorn entry
docker-compose.yml       # postgres, redis, qdrant
scripts/                 # preflight, swiggy_login (OAuth PKCE), migrate_qdrant,
│                        # install_launchd
src/
├── app.py               # FastAPI factory + lifespan (owns all resources)
├── api/                 # chat (SSE + resume), system (/status /metrics /preflight),
│                        # frames (WS), uploads, events, auth, threads, panels
├── graph/               # swarm (6 agents), middleware (resilience/clock/bridges),
│                        # guarded handoffs, state, build (parent graph)
├── memory/              # mem0 client, recall node, post-turn, history indexing
├── rag/                 # qdrant, embeddings, ingestion, retrieval tools, web cache
├── services/            # llm_registry (providers/slots/cooldown), mcp_providers,
│                        # metrics, redis, stores, event broker, guardian, schedulers
├── tools/               # vision, system, orders, reminders, shopping, music, progress
├── prompts/             # per-agent system prompts + unavailable notes
└── configs/             # settings (pydantic), llm factories, logging
web/                     # React 19 + TS + Vite SPA: tokens.css design system with
│                        # dark mode, chat, settings, setup wizard, time travel,
│                        # HITL approvals, camera/voice panels · Vitest + RTL tests
tests/                   # hermetic pytest suite (fakes for LLM/Redis/Qdrant/Mem0)
docs/                    # architecture, setup, providers, mcp, infrastructure, api
```

---

## Tech stack

Python 3.11+ · `uv` · LangGraph + `langgraph-swarm` · LangChain agents ·
`deepagents` · FastAPI + SSE · React 19 + TypeScript + Vite · PostgreSQL
(`langgraph-checkpoint-postgres`) · Redis · Qdrant · Mem0 · llama.cpp / Ollama /
OpenAI / Anthropic / Gemini.

## Notes

- macOS host features (`say`, `open -a`, webcam) require running the app on the
  host, not in a container — hence the hybrid Docker setup.
- Switching embedding providers is non-destructive: collections are
  dimension-suffixed (`documents_768` vs `documents_1536`); clean up orphans
  with `uv run python scripts/migrate_qdrant.py --list`.
