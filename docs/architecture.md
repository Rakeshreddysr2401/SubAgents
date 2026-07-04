# Architecture

SubAgents is a production-oriented multimodal visual assistant. A **swarm** of
specialist agents (built on `langgraph-swarm`) collaborates through guarded
handoffs, wrapped by a Mem0 recall step, and served by a standalone FastAPI app
that streams tokens over SSE and persists everything to Postgres, Redis, and
Qdrant.

## High-level flow

```
Browser SPA (static/index.html)
   │  POST /chat (SSE token deltas)   WS /ws/frames   GET /events   POST /upload
   ▼
FastAPI (uvicorn on macOS host, port 2024)   main.py → src/app.py
   │  lifespan owns: AsyncPostgresSaver, Redis, Qdrant, Mem0, MCP tools, graph
   ▼
LangGraph parent graph
   START → recall_memories (Mem0 search) → assistant (swarm) → END
                                              │
        ┌─────────────────────────────────────┼─────────────────────────────┐
        ▼                                      ▼                             ▼
   conversation (default) ────transfer────► swiggy ────transfer────► tracker
        ▲                                      │                             │
        └──────────────── guarded handoffs (transfer_to_*) ─────────────────┘
   ▼
Post-turn background pipeline (BackgroundTasks)
   Mem0 write · turn-summary → Qdrant history · webcam-frame → Qdrant history
```

## Turn lifecycle

1. `POST /chat` authenticates (JWT → `user_id`), rate-limits, validates the
   `thread_id`, and starts `graph.astream(..., stream_mode=["messages","updates"])`.
2. **recall_memories** searches Mem0 for memories relevant to the latest user
   message and writes them into `recalled_memories`.
3. The **swarm** routes to the active agent (sticky) or the default
   (`conversation`). Each agent's prompt surfaces `recalled_memories` as
   "What you remember about this user".
4. Agents stream tokens; the handler forwards each as `{"delta": "..."}` SSE
   events, filtering tool-call chunks. On completion it emits
   `{"done", thread_id, active_agent}`.
5. After the response is sent, a **background task** writes the exchange to Mem0
   and indexes a turn summary (and any webcam frame) into Qdrant `history`.

## Handoffs, sticky routing, loop guard

- Agents transfer control with `transfer_to_<agent>(reason=...)` tools
  (`src/graph/handoff.py`). Each emits `Command(goto=..., graph=Command.PARENT)`,
  which resolves to the swarm even though the swarm is itself a subgraph of the
  parent recall graph.
- The receiving agent gets a **bridge** `SystemMessage` explaining why it now
  owns the turn. Stale bridges from earlier turns are pruned before each model
  call (`KeepOnlyLatestBridge` middleware).
- **Sticky**: the last active agent handles the next user turn directly
  (swarm-native, persisted via `active_agent` in the checkpoint).
- **Loop guard**: `agent_turn_visits` (reset to `{}` on every `/chat` input)
  counts handoffs per agent per turn. Past `MAX_AGENT_VISITS` (default 3) a
  handoff is *refused* with a ToolMessage telling the agent to answer directly.

## State schema

`src/graph/state.py`

| Channel | Purpose |
|---|---|
| `messages` | conversation (add_messages reducer) |
| `active_agent` | sticky routing target (SwarmState) |
| `always_speak` | TTS toggle for the turn |
| `agent_turn_visits` | per-turn loop-guard counters |
| `recalled_memories` | Mem0 hits injected by `recall_memories` |

## Persistence & data stores

| Store | Holds | Owner |
|---|---|---|
| PostgreSQL | LangGraph checkpoints (thread state) | `AsyncPostgresSaver` |
| Redis | latest webcam frame (TTL), web-search exact cache, rate-limit counters | `src/services/*` |
| Qdrant `documents` | uploaded-document chunks | RAG ingestion |
| Qdrant `history` | turn summaries + webcam-frame descriptions | post-turn pipeline |
| Qdrant `search_cache` | semantic web-search cache | `cached_web_search` |
| Qdrant `mem0_memories` | long-term user memories | Mem0 |

See [memory-and-rag.md](memory-and-rag.md) for the memory/RAG details and
[infrastructure.md](infrastructure.md) for the container topology.
