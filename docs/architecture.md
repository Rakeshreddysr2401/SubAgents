# Architecture

SubAgents is a production-oriented multimodal visual assistant. A **swarm** of
specialist agents (built on `langgraph-swarm`, plus a `deepagents`-based planner)
collaborates through guarded handoffs, wrapped by a Mem0 recall step, and served
by a standalone FastAPI app that streams tokens over SSE and persists everything
to Postgres, Redis, and Qdrant. A React SPA (`web/`) is the client, with live
agent/tool visualization and human-in-the-loop approval for risky tool calls.

## High-level flow

```
React SPA (web/, built to web/dist/, served by FastAPI for /, /login, /account)
   │  POST /chat (SSE)   POST /chat/resume   WS /ws/frames   GET /events   POST /upload
   │  /auth/* (signup, login, refresh, logout, me, change-password, account)
   │  /threads/* (list, messages, rename, delete)
   ▼
FastAPI (uvicorn on macOS host, port 2024)   main.py → src/app.py
   │  lifespan owns: AsyncPostgresSaver, Redis, Qdrant, Mem0, MCP tools, graph,
   │  a Postgres pool for users/chat_threads (src/services/db.py)
   ▼
LangGraph parent graph
   START → recall_memories (Mem0 search) → assistant (swarm) → END
                                              │
        ┌─────────────┬────────────────────┬─┴──────────────────┐
        ▼             ▼                    ▼                    ▼
   conversation ◄─transfer─► swiggy ◄─transfer─► tracker ◄─transfer─► planner
   (default)                                                    (deepagents deep agent;
        ▲                                                        write_todos/task tools)
        └──────────────── guarded handoffs (transfer_to_*), all-to-all ─────┘
   Any agent's gated tool call (GATED_TOOL_NAMES) pauses via interrupt() for
   human approval — resumed via POST /chat/resume
   ▼
Post-turn background pipeline (BackgroundTasks)
   Mem0 write · turn-summary → Qdrant history · webcam-frame → Qdrant history
```

## Turn lifecycle

1. `POST /chat` authenticates (cookie or bearer JWT → `user_id`, see
   [Auth & Sessions](../CLAUDE.md#auth--sessions-src-apiauthpy)), rate-limits,
   validates the `thread_id`, records/touches that thread's ownership row
   (`chat_threads`, title derived from the first message), and starts
   `graph.astream(..., stream_mode=["messages","updates"])` via the shared
   `_stream_graph_events` generator (`src/api/chat.py`).
2. **recall_memories** searches Mem0 for memories relevant to the latest user
   message and writes them into `recalled_memories`.
3. The **swarm** routes to the active agent (sticky) or the default
   (`conversation`). Each agent's prompt surfaces `recalled_memories` as
   "What you remember about this user".
4. Agents stream tokens (`{"delta": ...}`), live agent changes (`{"agent": ...}`),
   and tool activity (`{"tool_call": ...}` / `{"tool_result": ...}`, deduped by id
   since `updates` fires once per nested graph level). If a gated tool call fires,
   `{"interrupt": ...}` is emitted instead of `{"done"}`, and the turn pauses until
   `POST /chat/resume` supplies a decision. On completion:
   `{"done", thread_id, active_agent}`.
5. After the response is sent, a **background task** writes the exchange to Mem0
   and indexes a turn summary (and any webcam frame) into Qdrant `history`
   (skipped for a turn that's still paused on an interrupt).

## Handoffs, sticky routing, loop guard

- Agents transfer control with `transfer_to_<agent>(reason=...)` tools
  (`src/graph/handoff.py`). Each emits `Command(goto=..., graph=Command.PARENT)`,
  which resolves to the swarm even though the swarm is itself a subgraph of the
  parent recall graph. The planner is a normal swarm peer for this purpose too —
  `create_deep_agent()`'s output is a `CompiledStateGraph` with a `tools` node
  `langgraph_swarm` inspects for handoff metadata like any other agent.
- The receiving agent gets a **bridge** `SystemMessage` explaining why it now
  owns the turn. Stale bridges from earlier turns are pruned before each model
  call (`KeepOnlyLatestBridge` middleware).
- **Sticky**: the last active agent handles the next user turn directly
  (swarm-native, persisted via `active_agent` in the checkpoint).
- **Loop guard**: `agent_turn_visits` (reset to `{}` on every `/chat` input)
  counts handoffs per agent per turn. Past `MAX_AGENT_VISITS` (default 3) a
  handoff is *refused* with a ToolMessage telling the agent to answer directly.

## Human-in-the-loop approvals

Every agent (including the planner) carries `HumanInTheLoopMiddleware(interrupt_on=
GATED_TOOL_NAMES)` (`src/commons/constants.py`). A gated tool call (e.g.
`open_mac_app`) triggers LangGraph's `interrupt()` before execution; the resulting
`{"__interrupt__": ...}` bubbles up through all 3 nested graph levels (parent →
swarm → react agent) and is deduped/surfaced as one `{"interrupt": ...}` SSE event.
The client resolves it via `POST /chat/resume?thread_id=...` with a `decisions`
list (`approve`/`edit`/`reject`/`respond`), which the backend turns into
`Command(resume={"decisions": [...]})` against the same thread config — resuming
the persisted checkpoint exactly where it paused. See
[CLAUDE.md → Human-in-the-loop approvals](../CLAUDE.md#human-in-the-loop-approvals)
for the exact wire shapes.

## State schema

`src/graph/state.py`

| Channel | Purpose |
|---|---|
| `messages` | conversation (add_messages reducer) |
| `active_agent` | sticky routing target (SwarmState) |
| `always_speak` | TTS toggle for the turn |
| `agent_turn_visits` | per-turn loop-guard counters |
| `recalled_memories` | Mem0 hits injected by `recall_memories` |

The planner's own subgraph uses `PlannerAgentState(DeepAgentState)`, which adds
`deepagents`' `todos`/filesystem channels on top of the same `agent_turn_visits`/
`recalled_memories` extras the other agents' `VisualAgentState` carries.

## Server-push events, reminders, guardian

Beyond the per-request SSE chat stream, the app has a persistent, per-user
push channel: `GET /events` (authenticated). All payloads are JSON with a
`type` key (see [api.md](api.md) for the table); fan-out happens in the
module-level `EventBroker` (`src/services/event_broker.py`) so tools and
background loops can push without touching `app.state`. The React client owns
exactly one subscription (`web/src/components/EventsBridge.tsx`) and
dispatches by type into zustand stores (toasts, music player, guardian state,
panel refresh bumps). Assistant replies, reminders and guardian alerts are
spoken in the browser via speechSynthesis (`web/src/lib/tts.ts`); the host
Mac's `say` is opt-in via `HOST_TTS_ENABLED`.

Two lifespan-owned asyncio loops run alongside the server:

- **Reminder scheduler** (`src/services/reminder_scheduler.py`): every
  `REMINDER_POLL_SECONDS` it atomically claims due rows from `reminders`
  (`UPDATE … WHERE status='pending' … RETURNING`, so overlapping ticks can't
  double-fire) and pushes a `reminder` event to the owner.
- **Guardian watcher** (`src/services/guardian.py`): for each user with
  guardian mode on (Redis set), pulls the latest webcam frame and asks the
  vision model whether anything looks concerning vs. the previous
  observation; concerns become `guardian_alert` events, cooldown-limited.

On Zomato (PRD wish): Zomato has no public API, so there is deliberately no
fake integration — restaurant discovery beyond Swiggy goes through
`cached_web_search`, and a future Zomato MCP server would plug into the same
`load_swiggy_tools`/`apply_swiggy_tools` slot the Swiggy MCP uses.

## Persistence & data stores

| Store | Holds | Owner |
|---|---|---|
| PostgreSQL | LangGraph checkpoints (thread state) | `AsyncPostgresSaver` |
| PostgreSQL `users` | account email + bcrypt password hash | `src/services/user_store.py` |
| PostgreSQL `chat_threads` | thread ownership, title, last-active — the sidebar's data | `src/services/thread_store.py` |
| PostgreSQL `reminders` | scheduled reminders (pending/fired/cancelled) | `src/services/reminder_store.py` |
| PostgreSQL `shopping_items` | per-user shopping list | `src/services/shopping_store.py` |
| Redis | latest webcam frame (TTL), web-search exact cache, rate-limit counters, `refresh_token:<jti>` → user_id (revocable sessions), guardian-mode state, geocode cache | `src/services/*` |
| Qdrant `documents` | uploaded-document chunks | RAG ingestion |
| Qdrant `history` | turn summaries + webcam-frame descriptions | post-turn pipeline |
| Qdrant `search_cache` | semantic web-search cache | `cached_web_search` |
| Qdrant `mem0_memories` | long-term user memories | Mem0 |

The `users`/`chat_threads` tables live in a separate `psycopg_pool` connection
pool from the LangGraph checkpointer (`src/services/db.py`) — same Postgres
instance, independent connections. Thread ownership is metadata layered on top
of the checkpointer's own thread_id keying; deleting a `chat_threads` row hides
a conversation from the sidebar but doesn't purge the underlying checkpoint.

See [memory-and-rag.md](memory-and-rag.md) for the memory/RAG details,
[infrastructure.md](infrastructure.md) for the container topology, and
[CLAUDE.md → Auth & Sessions](../CLAUDE.md#auth--sessions-src-apiauthpy) for
the full auth design.
