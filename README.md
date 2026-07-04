# SubAgents — Production-Ready AI Visual Assistant

A locally-run, multimodal AI assistant built on **LangGraph** (swarm
orchestration), **FastAPI** (standalone runtime with real token streaming), and
a durable memory stack: **PostgreSQL** (checkpoints), **Redis** (frame buffer &
caches), **Qdrant** (vectors), and **Mem0** (long-term memory). A swarm of
specialist agents collaborates through guarded handoffs to handle general
queries, vision, food ordering, and delivery tracking — with persistent memory
and retrieval-augmented reasoning.

---

## Key Features

- **Swarm multi-agent coordination** — `langgraph-swarm` with sticky routing and
  guarded `transfer_to_*` handoffs (loop guard + reason bridges). Agents:
  `conversation` (default/router), `swiggy`, `tracker`.
- **Real token streaming** — in-process graph via `graph.astream`, streamed to
  the browser as SSE `{"delta": ...}` events.
- **Long-term memory (Mem0)** — user-scoped facts recalled every turn and
  written after each exchange, backed by Qdrant.
- **RAG** — upload documents (`/upload`), ask questions over them
  (`search_documents`); recall past conversations and things shown to the camera
  (`recall_history`); cached web search (Redis exact + Qdrant semantic + Tavily).
- **Multimodal perception** — live webcam vision (`capture_webcam`) with frames
  buffered in Redis with a TTL.
- **Durable persistence** — Postgres checkpointer; state survives restarts.
- **Auth & rate limiting** — JWT `user_id` scoping; per-user rate limits.
- **Local-first** — runs entirely on local models (Ollama/llama.cpp) or OpenAI.

---

## Quickstart

```bash
docker compose up -d               # Postgres, Redis, Qdrant (wait for healthy)
uv sync                            # install dependencies
cp .env.example .env               # configure LLM + embedding providers
uv run uvicorn main:app --port 2024
```

Open <http://localhost:2024>. Full setup (LLM/embedding options, wake word) is in
**[docs/setup.md](docs/setup.md)**.

---

## Architecture at a glance

```
Browser SPA ── POST /chat (SSE) · WS /ws/frames · GET /events · POST /upload
   ▼
FastAPI (host, :2024)   main.py → src/app.py   [lifespan owns all resources]
   ▼
Parent graph:  START → recall_memories (Mem0) → swarm → END
   swarm:  conversation (default) ⇄ swiggy ⇄ tracker   (guarded handoffs)
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
| [docs/infrastructure.md](docs/infrastructure.md) | Containers, volumes, backup, resilience |
| [docs/memory-and-rag.md](docs/memory-and-rag.md) | Mem0, RAG collections, embedding-dim invariant |
| [docs/api.md](docs/api.md) | Endpoint + SSE contract reference |
| [CLAUDE.md](CLAUDE.md) | Developer/AI implementation reference |

---

## Project layout

```
main.py                  # uvicorn entry
docker-compose.yml       # postgres, redis, qdrant
src/
├── app.py               # FastAPI factory + lifespan (owns all resources)
├── api/                 # chat (SSE), frames (WS), uploads, events, auth, deps
├── graph/               # swarm, guarded handoffs, state, build (parent graph)
├── memory/              # mem0 client, recall node, post-turn, history indexing
├── rag/                 # qdrant, embeddings, ingestion, retrieval tools, web cache
├── services/            # redis client, frame buffer (TTL), rate limit, tts
├── tools/               # vision, system, swiggy MCP loader, tool sets
├── prompts/             # per-agent system prompts
└── configs/             # settings (pydantic), llm factories, logging
tests/                   # hermetic pytest suite (fakes for LLM/Redis/Qdrant/Mem0)
docs/                    # architecture, setup, infrastructure, memory-and-rag, api
```

---

## Tech stack

Python 3.11+ · `uv` · LangGraph + `langgraph-swarm` · LangChain agents ·
FastAPI + SSE · PostgreSQL (`langgraph-checkpoint-postgres`) · Redis · Qdrant ·
Mem0 · Ollama / llama.cpp / OpenAI.

## Notes

- macOS host features (`say`, `open -a`, webcam) require running the app on the
  host, not in a container — hence the hybrid Docker setup.
- Conversation history from the old `langgraph dev` runtime (`.langgraph_api/`
  pickles) is **not** migrated to Postgres; it starts fresh.
