# SubAgents — Production-Ready AI Visual Assistant

A locally-run, multimodal AI assistant built on **LangGraph** (swarm
orchestration), **`deepagents`** (planning), **FastAPI** (standalone runtime with
real token streaming), a **React** SPA, and a durable memory stack:
**PostgreSQL** (checkpoints), **Redis** (frame buffer & caches), **Qdrant**
(vectors), and **Mem0** (long-term memory). A swarm of specialist agents
collaborates through guarded handoffs to handle general queries, vision, food
ordering, delivery tracking, and multi-step planning — with persistent memory,
retrieval-augmented reasoning, and human-in-the-loop approval for risky actions.

---

## Key Features

- **Swarm multi-agent coordination** — `langgraph-swarm` with sticky routing and
  guarded `transfer_to_*` handoffs (loop guard + reason bridges). Agents:
  `conversation` (default/router), `swiggy`, `tracker`, and `planner` (a real
  `deepagents` deep agent for multi-step task decomposition).
- **Live agent & tool visualization** — the React chat UI shows which agent is
  active and streams tool calls/results in real time instead of a plain spinner.
- **Human-in-the-loop approvals** — risky tool calls (e.g. opening an app) pause
  for approve/edit/reject before executing, via LangGraph `interrupt()` +
  `POST /chat/resume`.
- **Real token streaming** — in-process graph via `graph.astream`, streamed to
  the browser as SSE (`delta`/`agent`/`tool_call`/`tool_result`/`interrupt`/`done`).
- **Long-term memory (Mem0)** — user-scoped facts recalled every turn and
  written after each exchange, backed by Qdrant.
- **RAG** — upload documents (`/upload`), ask questions over them
  (`search_documents`); recall past conversations and things shown to the camera
  (`recall_history`); cached web search (Redis exact + Qdrant semantic + Tavily).
- **Multimodal perception** — live webcam vision (`capture_webcam`) with frames
  buffered in Redis with a TTL; camera preview and wake-word status in the UI.
- **It speaks** — replies are read aloud in the browser (speechSynthesis) when
  voice mode is on; reminders and guardian alerts are spoken too.
- **Reminders** — "remind me at 5 to go to the movie" schedules a Postgres-backed
  reminder; when due, the browser shows a persistent toast and says it out loud.
- **Shopping list** — "remember we need to buy soap" maintains a real per-user
  list (panel with checkboxes); the swiggy agent consults it when ordering
  groceries and ticks items off after ordering.
- **Music & news** — internet-radio playback in the browser controlled by voice
  ("play some music"), and date-fresh news summaries via `get_latest_news`.
- **Location aware** — browser geolocation (opt-in) flows to tools;
  `get_current_location` reverse-geocodes via OpenStreetMap for "near me" asks.
- **Guardian mode** — toggle the shield (or say "watch my room"): the backend
  watches the camera with the vision model and alerts you (toast + voice) if
  something looks wrong, with an alert cooldown.
- **Per-user server push** — an authenticated `/events` SSE channel routes
  reminders/music/guardian events only to their owner's browser tabs.
- **Durable persistence** — Postgres checkpointer; state survives restarts.
- **Real accounts & sessions** — signup/login pages, httpOnly-cookie JWT
  sessions with rotating refresh tokens, per-user conversation history sidebar,
  and an account settings page (change password / delete account).
- **Rate limiting** — per-user limits on `/chat`/`/upload`; brute-force limits
  on `/auth/login`/`/auth/signup`.
- **Local-first** — runs entirely on local models (Ollama/llama.cpp) or OpenAI.

---

## Quickstart

```bash
docker compose up -d               # Postgres, Redis, Qdrant (wait for healthy)
uv sync                            # install backend dependencies
cp .env.example .env               # configure LLM + embedding providers
uv run uvicorn main:app --port 2024

# React frontend — build once for production, or run its own dev server:
cd web && npm install && npm run build   # -> web/dist/, served by FastAPI above
# or, for frontend hot-reload during development (proxies API calls to :2024):
cd web && npm run dev                    # -> http://localhost:5173
```

Open <http://localhost:2024> (or the Vite dev URL if using `npm run dev`). With
`AUTH_DISABLED=true` (the dev default) you land straight in the chat UI; set it
to `false` to require real signup/login. Full setup (LLM/embedding options,
auth, wake word) is in **[docs/setup.md](docs/setup.md)**.

---

## Architecture at a glance

```
React SPA (web/) ── POST /chat (SSE) · POST /chat/resume · WS /ws/frames
                  ── GET /events · POST /upload
                  ── /auth/* (signup, login, refresh, logout, account) · /threads/*
   ▼
FastAPI (host, :2024)   main.py → src/app.py   [lifespan owns all resources;
                                                 also serves web/dist/ for /, /login, /account]
   ▼
Parent graph:  START → recall_memories (Mem0) → swarm → END
   swarm:  conversation (default) ⇄ swiggy ⇄ tracker ⇄ planner   (guarded handoffs)
           risky tool calls pause via interrupt() for human approval
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
| [docs/learning-roadmap.md](docs/learning-roadmap.md) | Phase-2 preference-learning design (no code yet) |
| [CLAUDE.md](CLAUDE.md) | Developer/AI implementation reference |

---

## Project layout

```
main.py                  # uvicorn entry
docker-compose.yml       # postgres, redis, qdrant
src/
├── app.py               # FastAPI factory + lifespan (owns all resources); serves
│                        # web/dist/ for /, /login, /account
├── api/                 # chat (SSE + resume), frames (WS), uploads, events, auth, threads, deps
├── graph/               # swarm (incl. planner + HITL), guarded handoffs, state, build (parent graph)
├── memory/              # mem0 client, recall node, post-turn, history indexing
├── rag/                 # qdrant, embeddings, ingestion, retrieval tools, web cache
├── services/            # redis client, frame buffer (TTL), rate limit, tts,
│                        # security (bcrypt + JWT), db/user_store/thread_store (auth)
├── tools/               # vision, system, swiggy MCP loader, tool sets
├── prompts/             # per-agent system prompts (incl. planner)
└── configs/             # settings (pydantic), llm factories, logging
web/                     # React 19 + TypeScript + Vite SPA — auth, chat, threads,
│                        # live agent/tool visualization, HITL approval UI, plan
│                        # tracker, camera/voice panels (see web/src/)
tests/                   # hermetic pytest suite (fakes for LLM/Redis/Qdrant/Mem0/auth stores)
docs/                    # architecture, setup, infrastructure, memory-and-rag, api
```

---

## Tech stack

Python 3.11+ · `uv` · LangGraph + `langgraph-swarm` · LangChain agents ·
`deepagents` · FastAPI + SSE · React 19 + TypeScript + Vite · PostgreSQL
(`langgraph-checkpoint-postgres`) · Redis · Qdrant · Mem0 · Ollama / llama.cpp /
OpenAI.

## Notes

- macOS host features (`say`, `open -a`, webcam) require running the app on the
  host, not in a container — hence the hybrid Docker setup.
- Conversation history from the old `langgraph dev` runtime (`.langgraph_api/`
  pickles) is **not** migrated to Postgres; it starts fresh.
