# CLAUDE.md — Developer & AI Reference

Technical reference for the SubAgents codebase. Read this before making changes.

---

## Quick Facts

- **Runtime**: Python 3.11+, managed with `uv`; React 19 + TypeScript + Vite frontend in `web/`, managed with `npm`
- **Framework**: LangGraph + `langgraph-swarm` (graph), LangChain agents, `deepagents`
  (planner), FastAPI (standalone API); LLM providers: llama_cpp (any
  OpenAI-compatible server, default) / openai / anthropic / gemini / ollama via
  `src/services/llm_registry.py`, with per-agent llama.cpp slot pinning and a
  cooldown-based cloud fallback (see [docs/providers.md](docs/providers.md))
- **Start command (backend)**: `uv run uvicorn main:app --port 2024`
- **Start command (frontend dev)**: `cd web && npm run dev` (Vite proxies API routes to
  `:2024`, see `web/vite.config.ts`) — in prod, `npm run build` output (`web/dist/`) is
  served directly by FastAPI, no separate frontend server
- **Entry**: `main.py` → `src/app.py:create_app()`; graph built in the lifespan
- **6 agents**: conversation (default/router), swiggy, instamart, dineout, tracker,
  planner (real `deepagents` deep agent, with an optional `research` subagent) —
  coordinated as a swarm
- **Stores**: Postgres (checkpoints + users/chat_threads/reminders/shopping_items),
  Redis (frames/cache/rate-limit/refresh-tokens/guardian-state/geocode-cache), Qdrant (RAG + Mem0)
- **Auth**: cookie-based JWT sessions with a real signup/login UI — see [Auth & Sessions](#auth--sessions-src-apiauthpy)
- **HITL**: risky tool calls (e.g. `open_mac_app`) pause for human approval via
  `interrupt()` — see [Human-in-the-loop approvals](#human-in-the-loop-approvals)
- **Server push**: authenticated per-user `/events` SSE (JSON `{"type": ...}`
  payloads) via the module-level `EventBroker`; browser speaks via
  speechSynthesis — see [Events, reminders, guardian, music, location](#events-reminders-guardian-music-location)

---

## Folder Structure

```
main.py                  # uvicorn entry (app = create_app())
docker-compose.yml       # postgres, redis, qdrant
src/
├── app.py               # FastAPI factory + lifespan (owns all long-lived resources);
│                        # serves web/dist/ (React build) for /, /login, /account
├── api/                 # chat (SSE + /chat/resume), frames, uploads, events, auth, threads,
│                        # reminders, shopping, music, guardian, deps
├── graph/               # state, handoff, middleware (resilience/clock/bridges), swarm
│                        # (6 agents incl. planner + HITL), build (parent graph)
├── memory/              # mem0_client, recall, post_turn, history_index
├── rag/                 # qdrant, embeddings, store, ingestion, retrieval_tools, web_cache
├── services/            # llm_registry (providers/slots/cooldown), mcp_providers,
│                        # metrics, redis_client, frame_buffer, rate_limit, security,
│                        # db, user_store, thread_store, reminder_store, shopping_store,
│                        # event_broker, reminder_scheduler, guardian
├── tools/               # vision, system, order (set_active_order), reminder, shopping,
│                        # music, news, location, guardian, progress, __init__ (tool sets)
├── prompts/             # conversation, swiggy, instamart, dineout, tracker, planner
│                        # (build_prompt() -> str; ordering agents also export
│                        # UNAVAILABLE_NOTE for the provider-down prompt swap)
├── commons/constants.py # agent name strings + AGENT_DESCRIPTIONS + GATED_TOOL_NAMES
├── models/schema.py     # pydantic request/response
└── configs/             # settings.py (pydantic-settings), llm.py, logging_config.py
web/                     # React 19 + TypeScript + Vite SPA (full replacement of the old
│                        # static/ HTML pages) — see web/src/, built to web/dist/
tests/                   # hermetic pytest suite
docs/                    # architecture, setup, infrastructure, memory-and-rag, api
```

---

## Runtime & Lifespan (`src/app.py`)

Everything long-lived is created in the FastAPI **lifespan** and stored on
`app.state`:

1. `AsyncPostgresSaver.from_conn_string(dsn)` + `await checkpointer.setup()`
2. Shared Redis client (`src/services/redis_client.get_redis()`)
3. Shared Qdrant client + `ensure_collections()` (creates + dim-checks)
4. Mem0 (`make_mem0()`) — best-effort; graph runs if it fails
5. `load_provider_tools("swiggy_food"/"swiggy_instamart"/"swiggy_dineout")`
   (async, `src/services/mcp_providers.py`) → `apply_mcp_tools(...)` — **no
   import-time network calls**, and no token → zero network
6. `build_graph(checkpointer, mem0)` — must run AFTER `apply_mcp_tools`
7. `asyncio.Queue()` for wake-word events

Shared module-level Redis/Qdrant clients let tools reach them without threading
`app.state` through the graph.

---

## Graph (`src/graph/`)

### Parent graph (`build.py`)

```
START → recall_memories → assistant(swarm) → END
```

- `recall_memories` (`src/memory/recall.py`) is async-only. **Invoke the graph
  with `astream`/`ainvoke`**, never sync `invoke`.
- The swarm is compiled as a subgraph node.

### Swarm (`swarm.py`)

- Conversation/swiggy/tracker built with `create_agent(get_llm(name), tools,
  middleware=[...], state_schema=VisualAgentState, name=...)` — passing the agent
  name to `get_llm` pins that agent's llama.cpp KV-cache slot (`LLM_SLOTS`) and
  applies `AGENT_LLM_OVERRIDES`. Middlewares per agent (all in
  `src/graph/middleware.py`, each implementing **both** `wrap_model_call` and
  `awrap_model_call`), in this order:
  - `dynamic_prompt` — the STATIC base prompt (+ the rare provider-unavailable
    note). Nothing per-turn goes in here: prompt content invalidates the whole
    llama.cpp KV prefix.
  - `ResilientModelMiddleware` — pi5-style fallback policy: primary in its 60s
    post-failure cooldown → route to `get_fallback_llm()` (FALLBACK_LLM_*);
    connection error → one retry, then cooldown + fallback; request-shaped error →
    no fallback; total failure → degraded `AIMessage` (never raises, SSE stays
    `delta`+`done`). Outermost wrapper so retries re-run the inner transforms.
  - `SummarizationMiddleware` — long-thread compaction (not on the planner).
  - `KeepOnlyLatestBridge` — prunes stale handoff bridges.
  - `StripImagesMiddleware` (all agents EXCEPT conversation) — replaces camera
    image blocks with a stable text placeholder, request-only: text agents
    never pay frame token costs in their KV slots; conversation keeps frames.
  - `LiveClockMiddleware` — appends ALL per-turn context (recalled memories +
    minute-rounded clock) as a **trailing SystemMessage**: only the tail
    re-prefills each turn, the prompt + history prefix stays cached. Must sit
    inside KeepOnlyLatestBridge.
  - `HumanInTheLoopMiddleware(interrupt_on=GATED_TOOL_NAMES)` — pauses on gated tool
    calls (see [Human-in-the-loop approvals](#human-in-the-loop-approvals)).
- **Planner** built with `deepagents.create_deep_agent(model, tools, system_prompt=...,
  middleware=[...], state_schema=PlannerAgentState, name="planner")` instead of
  `create_agent` — it's a real `deepagents` deep agent (ships `write_todos`,
  `task`, filesystem tools) composed as a normal swarm peer. Verified (Phase 0 spike)
  that `create_deep_agent()`'s output is a `CompiledStateGraph` with a `tools` node
  `langgraph_swarm` can inspect for handoff metadata like any other agent — no special
  wrapping needed. Use `system_prompt=`, not the `dynamic_prompt` middleware pattern,
  for the planner's custom instructions: it composes in front of deepagents' own
  default deep-agent prompt instead of replacing it.
- `create_swarm([conversation, swiggy, instamart, dineout, tracker, planner],
  default_active_agent="conversation", state_schema=VisualAssistantState)`. All six
  agents get `transfer_to_*` handoff tools to every other agent (dineout deliberately
  has no `transfer_to_tracker` — reservations aren't deliveries). The planner may also
  register a `research` deepagents subagent (utility model + web/doc search) when
  Tavily is configured; deepagents injects its own SummarizationMiddleware, so the
  planner must NOT get ours (duplicate-middleware assertion).

### Guarded handoffs (`handoff.py`)

`create_guarded_handoff_tool(agent_name)` → `transfer_to_<agent>(reason, ...)`:
- Increments `agent_turn_visits[agent]`.
- Past `settings.max_agent_visits` (3) → **refuses** via ToolMessage (no `goto`).
- Otherwise emits `Command(goto=agent, graph=Command.PARENT, update={messages: [*state.messages, tool_msg, bridge], active_agent, agent_turn_visits})`.
- `Command.PARENT` resolves to the **swarm** even though the swarm is nested
  inside the parent recall graph (verified by `tests/test_graph_routing.py`).

### State (`state.py`)

`VisualAssistantState(SwarmState)`: `messages`, `active_agent`, `always_speak`,
`agent_turn_visits`, `recalled_memories`. `VisualAgentState(AgentState)` mirrors
the extra channels for the react subgraphs. `PlannerAgentState(DeepAgentState)`
(deepagents' own state schema, which adds a delta-channel `messages` reducer plus
`todos`/filesystem channels via its own middleware) mirrors the same extra channels
for the planner.

---

## Streaming (`src/api/chat.py`)

`_stream_graph_events(app, graph_input, config, ...)` is a shared generator used by
both `/chat` (fresh turn, `graph_input` is the normal inputs dict) and `/chat/resume`
(resuming an interrupted turn, `graph_input` is `Command(resume={"decisions": [...]})`
built from the same `thread_id`/config). Both call
`graph.astream(graph_input, config, stream_mode=["messages","updates","custom"],
subgraphs=True)`:
- `{"delta": text}` — `AIMessage` chunks with content and **no tool calls** (filters
  tool/handoff chunks and tool-node output).
- `{"progress": text}` — long tools push human-readable steps via
  `src/tools/progress.py::emit_progress` (LangGraph `get_stream_writer`; no-op
  outside a graph run).
- `{"agent": name}` — live `active_agent` changes, from `updates` payloads (explicit
  set, else agent node name).
- `{"tool_call": {"id","name","args","agent"}}` / `{"tool_result": {"id","name",
  "result_preview","agent"}}` — from `updates` payloads' `AIMessage.tool_calls` /
  `ToolMessage`s. Handoff tools (`transfer_to_*`) are excluded (the `agent` event
  already covers those). **Dedup by id** — with `subgraphs=True`, the same update
  fires once per graph level (parent → swarm → react agent), so the same tool
  call/result/interrupt would otherwise repeat up to 3x.
- `{"interrupt": {"id","action_requests","review_configs"}}` — a gated tool call is
  awaiting approval (see below); **no `{"done"}` follows in this turn**, and post-turn
  background work (Mem0/history) does not run yet.
- On completion: `{"done", thread_id, active_agent}`; on error/timeout: `{"error"}`.
- Wrapped in `asyncio.timeout(settings.chat_timeout_seconds)`.
- **Frontend contract**: `web/src/api/stream.ts` (fetch + `ReadableStream`, not
  `EventSource` — both endpoints are POSTs with a JSON body) appends `parsed.delta`
  raw and buffers partial SSE lines; unknown keys are ignored so new event types are
  additive. Do not switch tokens back to a `text` field — the old code joined `text`
  events with `\n`, which corrupts token streaming.

Post-turn work is a **FastAPI `BackgroundTasks`** task (not a bare
`asyncio.create_task`, which gets GC'd/cancelled under StreamingResponse).

---

## Human-in-the-loop approvals

`src/commons/constants.py::GATED_TOOL_NAMES` (`dict[str, bool]`) lists tool names
gated behind approval — `open_mac_app` plus `confirm_order` (the shared
order-placement tool name on the Swiggy food + instamart MCP servers — this is the
spend guardrail, enforced at the tool boundary rather than in prompts). Other MCP
cart-mutation names load dynamically at runtime (`src/services/mcp_providers.py`) —
`src/app.py`'s lifespan logs every loaded MCP tool's name at startup
(`"MCP tool available (%s): %s"`) so more can be enumerated and added once the MCP
servers are reachable.

- **Middleware**: `langchain.agents.middleware.HumanInTheLoopMiddleware(interrupt_on=
  GATED_TOOL_NAMES)`, attached to every agent (gating is by tool name,
  agent-agnostic — a gated tool is caught no matter which agent calls it).
  **Do not write custom `wrap_tool_call`/`awrap_tool_call` middleware for this** — the
  built-in class already exists and implements `aafter_model` (delegates to sync
  `after_model`), which is what makes it safe to use in this astream-only graph;
  its own `wrap_tool_call`/`awrap_tool_call` are NOT implemented (raise
  `NotImplementedError`), so don't reach for those hooks directly.
- **Flow**: on a gated tool call, `interrupt()` fires with a `HITLRequest`
  (`action_requests`, `review_configs`); this bubbles up through all 3 nested graph
  levels as `{"__interrupt__": (Interrupt(value=...),)}` in an `updates` payload —
  `chat.py` dedups by `Interrupt.id` and emits one `{"interrupt": ...}` SSE event.
- **Resume**: `POST /chat/resume?thread_id=...` with body `{"decisions": [...]}`
  (mirrors `langchain.agents.middleware.human_in_the_loop.Decision`: `{"type":
  "approve"}` / `{"type": "edit", "edited_action": {"name","args"}}` / `{"type":
  "reject", "message"?}` / `{"type": "respond", "message"}`). Builds
  `Command(resume={"decisions": [...]})` and calls `graph.astream` with the **same**
  `config` as the original call — resumes the persisted checkpoint at the interrupted
  node regardless of the parent→swarm→react-agent nesting (verified in
  `tests/test_hitl.py` and a live spike that actually ran `open_mac_app`).
- On **reject**, the real tool never runs — `HumanInTheLoopMiddleware` inserts a
  synthetic `ToolMessage` for that `tool_call_id` and the framework's `ToolNode`
  skips executing a call that already has a matching result.

---

## Auth & Sessions (`src/api/auth.py`)

Real signup/login backed by Postgres, not just JWT verification:

- **Storage**: `users` and `chat_threads` tables in Postgres, via a plain
  `psycopg_pool.AsyncConnectionPool` (`src/services/db.py::make_pool()` +
  `ensure_schema()`) — separate from the LangGraph checkpointer's own
  connection. `app.state.db/user_store/thread_store` are set in the lifespan.
- **Tokens**: `src/services/security.py` issues a short-lived **access token**
  (`ACCESS_TOKEN_TTL_MINUTES`, default 15) and a long-lived **refresh token**
  (`REFRESH_TOKEN_TTL_DAYS`, default 7), both HS256 JWTs carrying a `type`
  claim (`access`/`refresh`) — `decode_token()` rejects a token used as the
  wrong type. Refresh tokens are single-use: each `POST /auth/refresh` deletes
  the old Redis key (`refresh_token:<jti>` → user_id) and issues a new pair.
- **Cookies**: both tokens are set httpOnly (`access_token` on `/`,
  `refresh_token` scoped to `/auth`); `COOKIE_SECURE` must be `true` behind
  HTTPS in prod (defaults `false` for local http dev). A bearer header is also
  accepted (checked before the cookie) for non-browser clients.
- **`get_user_id`** (used everywhere else in the app) and **`get_current_claims`**
  (used by `/auth/me`, returns `{id, email}`) both take `credentials` (Bearer)
  and `request: Request = None` — the `= None` default matters: it lets unit
  tests call these functions directly with a real `Request`-free stand-in
  (see `tests/test_auth.py::_FakeRequest`) while FastAPI still injects the
  real `Request` in production regardless of the default.
- **Routes**: `/auth/{signup,login,refresh,logout,me,change-password}` +
  `DELETE /auth/account` (cascades to that user's `chat_threads`). Signup/login
  are rate-limited via the existing `enforce_rate_limit`.
- **Test seam**: `user_store`/`thread_store` are duck-typed — `PostgresUserStore`
  /`PostgresThreadStore` in prod, `InMemoryUserStore`/`InMemoryThreadStore` in
  tests (`src/services/user_store.py`, `src/services/thread_store.py`). No
  test spins up real Postgres for auth logic.
- **Thread ownership**: `src/api/chat.py` calls `thread_store.touch(...)` on
  every `/chat` call (creates the row with a title derived from the first
  message, or bumps `updated_at`). `GET /history/{id}` and everything in
  `src/api/threads.py` (list/rename/delete/read-messages) checks
  `thread.user_id == user_id` before touching graph state — a thread_id
  without a matching owner row 404s even if the checkpointer has data for it.
- **Frontend**: `web/src/components/auth/LoginPage.tsx` (combined login/signup) and
  `AccountPage.tsx` (change password / delete account), React Router routes in
  `web/src/App.tsx`. `web/src/state/AuthContext.tsx` calls `/auth/me` on load (no
  manual bearer-token field), `web/src/components/RequireAuth.tsx` redirects to
  `/login` if unauthenticated. Thread-history sidebar (`ThreadSidebar.tsx`) from
  `GET /threads` — list/rename/delete all wired (rename via the pre-existing
  `PATCH /threads/{id}`, which no UI called before this). `web/src/api/client.ts::
  authFetch()` — silent `POST /auth/refresh` + one retry on 401, else redirect to
  `/login`.
- **AUTH_DISABLED** (dev default) still short-circuits everything to
  `default_user`/`dev@localhost` — the auth routes work in that mode too
  (handy for exercising signup/login UI locally) but nothing is actually gated.
- **`/ws/frames`** (`src/api/frames.py`) is gated too: the WS handshake carries
  the `access_token` cookie automatically (same-origin), or a non-browser
  client can pass `?token=<jwt>`. Rejected with a close code *before* `accept()`
  if unauthenticated (4401) or if `thread_id` already belongs to a different
  user (4403). A brand-new thread_id has no owner row yet, so it's let through
  — ownership is attributed on the first `/chat` call via `thread_store.touch()`.

---

## Memory & RAG

See [docs/memory-and-rag.md](docs/memory-and-rag.md) for the full picture. Key
code seams:

- `src/rag/embeddings.py::get_embeddings()` — provider switch (cache with `lru_cache`).
- `src/rag/qdrant.py::ensure_collections()` — creates collections, **fails fast**
  on a vector-size mismatch.
- `src/rag/store.py` — `upsert_texts` / `search_texts` (user-scoped); tests patch
  `get_qdrant`/`get_embeddings` here.
- `src/memory/recall.py` — Mem0 search uses `filters={"user_id": ...}` (mem0 2.x
  rejects top-level `user_id`).
- `src/memory/mem0_client.py` — `AsyncMemory.from_config` is **sync** in mem0 2.x;
  wrapped in `asyncio.to_thread`. Extraction LLM is independent (`MEM0_LLM_PROVIDER`).

---

## Settings (`src/configs/settings.py`)

`pydantic-settings`, cached via `get_settings()`. `load_dotenv()` runs at import
so third-party libs see the same env. `embedding_dim` derives from the provider
(openai=1536, ollama=768 — ollama is the default) unless `EMBEDDING_DIM`
overrides; collection names are dim-suffixed via properties
(`documents_collection` → `documents_768`). Tests call
`get_settings.cache_clear()` around env monkeypatches. `AUTH_DISABLED=false`
with the placeholder `JWT_SECRET` auto-generates + persists a real secret at
`~/.subagents/jwt_secret` (0600; `SUBAGENTS_JWT_SECRET_FILE` overrides in
tests) — see [Auth & Sessions](#auth--sessions-src-apiauthpy) for
`ACCESS_TOKEN_TTL_MINUTES`, `REFRESH_TOKEN_TTL_DAYS`, `COOKIE_SECURE`.

---

## Tools (`src/tools/__init__.py`)

```python
CONVERSATION_TOOLS = [capture_webcam, get_system_info, open_mac_app,
                      get_current_location, search_documents, recall_history,
                      *REMINDER_TOOLS, *SHOPPING_TOOLS, *MUSIC_TOOLS,
                      *GUARDIAN_TOOLS, *web_tools]
_SWIGGY_BASE_TOOLS = [*SHOPPING_TOOLS, get_current_location, set_active_order]
SWIGGY_TOOLS    = [*_SWIGGY_BASE_TOOLS]      # + food MCP tools at startup
INSTAMART_TOOLS = [*_INSTAMART_BASE_TOOLS]   # + instamart MCP tools at startup
DINEOUT_TOOLS   = []                         # dineout MCP tools at startup
TRACKER_TOOLS   = [set_active_order]         # + _TRACKING_TOOL_NAMES whitelist
```

- Handoff tools are appended per-agent in `swarm.py`, not stored here.
- `apply_mcp_tools(food, instamart, dineout)` **composes** base + MCP lists —
  it must never plain-overwrite the lists, or import-time tools (shopping,
  location) get silently wiped at startup. The graph is built after it so
  ToolNodes snapshot the full lists. (`apply_swiggy_tools` is a food-only
  legacy alias.)
- **Tracker whitelist**: food + instamart MCP servers share tool names
  (`get_addresses`, `confirm_order`, …), so the tracker takes only the
  non-colliding read-only `_TRACKING_TOOL_NAMES` subset — never both full sets.
- `capture_webcam` is **async** (reads the Redis frame buffer).
- Tools that need the current user/thread take `config: RunnableConfig` and read
  `config["configurable"]["user_id"/"thread_id"/"location"]` (chat.py builds it).
  Stores are reached via module-level `configure_*/get_*` pairs (set in the
  lifespan; `InMemory*` twins in tests) — never via `app.state`.

---

## Events, reminders, guardian, music, location

- **`src/services/event_broker.py`** — module-level `EventBroker` singleton
  (`get_broker()`/`reset_broker()`): `subscribe(user_id)`, `broadcast(payload,
  user_id=None)` (None = all users). All payloads are JSON `{"type": ...}`;
  the client ignores unknown types, so new event types are additive. Full type
  table in `docs/api.md`. Must be called on the event loop (threads use
  `loop.call_soon_threadsafe`, see the wake-word listener in `src/app.py`).
- **`GET /events`** (`src/api/events.py`) is authenticated (`Depends(get_user_id)`)
  and per-user routed. The React client owns exactly ONE subscription:
  `web/src/components/EventsBridge.tsx` (headless; dispatches into zustand
  stores, silently refreshes the access token before reconnecting).
- **Browser TTS** — `web/src/lib/tts.ts::speak()` (speechSynthesis; strips
  markdown, chunks sentences because Chrome kills long utterances). Replies are
  spoken on the `done` SSE event when voice mode is on; reminders/guardian
  alerts are spoken from EventsBridge. The host Mac `say` path still exists but
  is opt-in (`HOST_TTS_ENABLED`, default false).
- **Reminders** — `reminders` table + `PostgresReminderStore`/`InMemoryReminderStore`
  (`src/services/reminder_store.py`); tools in `src/tools/reminder_tools.py`
  (LLM passes ISO-8601 — agents get a live clock line injected per model call
  by `_make_prompt_middleware` in `swarm.py`); lifespan-owned polling loop
  (`src/services/reminder_scheduler.py`, `REMINDER_POLL_SECONDS`) claims due
  rows atomically (`UPDATE … RETURNING`) so overlapping ticks can't double-fire.
  Panel REST: `GET/DELETE /reminders` (`src/api/reminders.py`).
- **Shopping list** — `shopping_items` table + store twins
  (`src/services/shopping_store.py`); name-matched tools
  (`src/tools/shopping_tools.py`, ambiguity returns candidates); REST
  `src/api/shopping.py`; in both `CONVERSATION_TOOLS` and `_SWIGGY_BASE_TOOLS`.
- **Guardian** (`src/services/guardian.py`) — Redis set `guardian:enabled` +
  per-user JSON state; lifespan loop every `GUARDIAN_INTERVAL_SECONDS` pulls
  `get_latest_frame(thread_id)` and asks **`get_vision_llm()`** (the dedicated
  VLM endpoint — `VISION_LLM_BASE_URL`/`VISION_MODEL`, defaulting to the
  llama.cpp mac-mini config; NOT `get_utility_llm()`) for a JSON verdict vs.
  the previous observation; alerts respect `GUARDIAN_ALERT_COOLDOWN_SECONDS`;
  no-frame is notified once until frames resume. REST `src/api/guardian.py` +
  voice tools `src/tools/guardian_tools.py` share the same state. Note:
  `capture_webcam` images still go to the *calling agent's* model (`get_llm()`)
  — keep the chat model multimodal, or vision questions in chat degrade.
- **Location** — `ChatRequest.location` (browser geolocation, optional) →
  `config["configurable"]["location"]` → `get_current_location`
  (`src/tools/location_tools.py`): Nominatim reverse geocode with a 1.1s
  rate-limit lock + 24h Redis cache, degrades to raw coords, never raises.
- **Music** — `MUSIC_STATIONS` (JSON in settings) → `play_music`/`stop_music`
  tools broadcast `music` events; playback is entirely browser-side
  (`web/src/components/panels/MusicPanel.tsx`, autoplay-block fallback).

---

## Adding a New Agent

`src/graph/registry.py::AGENT_SPECS` is the single source of truth —
`build_swarm_graph()` derives agents, tool sets and handoff wiring from it, and
`src/api/chat.py`'s sticky-routing detection derives from `constants.AGENTS`.

1. `src/prompts/{name}.py` with `build_prompt() -> str` (plus an
   `UNAVAILABLE_NOTE` constant if the agent depends on an MCP provider).
2. Add the name constant + `AGENTS` + `AGENT_DESCRIPTIONS` entries in
   `src/commons/constants.py`.
3. Add a `{NAME}_TOOLS` list in `src/tools/__init__.py` (and extend
   `apply_mcp_tools` if it carries MCP tools).
4. Add ONE `AgentSpec` entry to `AGENT_SPECS` (set `mcp_provider`, `vision`,
   `deep`, `no_handoff_to` as needed) — every other agent automatically gets a
   `transfer_to_<newname>` tool.
5. Update the other agents' prompts with routing rules for the new agent
   (LLM-facing text — the only step a table can't do).

`tests/test_registry.py` fails if constants/descriptions/specs drift apart.

---

## Common Pitfalls

- **Invoke the graph async** — `recall_memories` is async-only; sync `invoke`
  raises. Tests use `ainvoke`.
- **Build the graph after `apply_mcp_tools`** — otherwise the ordering agents and
  tracker have no MCP tools.
- **Middleware must implement both sync and async** `wrap_model_call` /
  `awrap_model_call` (we call `astream`).
- **Don't revive the `text` SSE field for tokens** — use `delta` (frontend
  joins `text` with newlines).
- **Embedding-dim invariant** — switching `EMBEDDING_PROVIDER` requires dropping
  Qdrant collections; startup asserts the sizes match.
- **Mem0 on local models** — extraction hallucinates; keep `MEM0_LLM_PROVIDER=openai`.
- **Loop guard** — >3 handoffs to one agent per turn is refused (not rerouted);
  `agent_turn_visits` resets via the `{}` passed in each `/chat` input.
- **Refresh tokens are single-use** — `POST /auth/refresh` deletes the old
  Redis key before issuing a new pair; replaying an old refresh token is
  treated as revoked/reused, not honored.
- **Thread ownership lives outside the checkpointer** — a `chat_threads` row
  must exist and match `user_id`, or `/history`, `/threads/*` all 404 even if
  the LangGraph checkpoint itself has data for that thread_id.
- **`HumanInTheLoopMiddleware`'s `wrap_tool_call`/`awrap_tool_call` are unimplemented
  stubs** — it hooks in via `after_model`/`aafter_model` instead. Don't write custom
  `wrap_tool_call` middleware expecting to intercept HITL-gated calls the same way.
- **`default_user` needs a `users` row when `AUTH_DISABLED=true`** —
  `src/services/db.py::ensure_schema()` upserts one (`id='default_user'`) precisely
  because nothing else creates it (no signup flow runs in that mode), and
  `chat_threads.user_id` has an FK to `users.id`.
- **`deepagents` requires langgraph>=1.2.7 / langchain>=1.3.11** — a real
  compatibility constraint (see `pyproject.toml`), not just a style preference.
- **`apply_mcp_tools` must compose, not overwrite** — it builds
  `[*_BASE_TOOLS, *mcp_tools]` per agent; a plain `SWIGGY_TOOLS[:] = mcp_tools`
  silently wipes the shopping/location/order tools registered at import time
  (guarded by `tests/test_shopping_tools.py::test_apply_swiggy_tools_keeps_base_tools`
  and `tests/test_mcp_providers.py`).
- **The live clock is a trailing message, not a prompt edit** — every agent
  (planner included) gets `LiveClockMiddleware`'s minute-rounded trailing
  SystemMessage. Don't move the clock back into the dynamic prompt: per-call
  prompt mutation invalidates the llama.cpp KV-cache prefix on every call.
- **LLM providers**: `LLM_PROVIDER` ∈ llama_cpp | openai | anthropic | gemini |
  ollama, built via `src/services/llm_registry.build_chat_model()`. Slot pinning
  (`LLM_SLOTS`) applies only to llama_cpp. `max_retries=0` on OpenAI-compatible
  clients is deliberate — retry policy lives in `ResilientModelMiddleware`.
- **`EventBroker.broadcast` is loop-affine** — like the old fan-out, it must run
  on the app's event loop; background threads bridge with
  `loop.call_soon_threadsafe` (wake-word listener does this).
- **`/events` payloads are JSON now** — a client checking
  `event.data === "start_voice"` (the pre-v0.8 string contract) breaks; parse
  JSON and switch on `type`.

---

## Tests

`uv run pytest`. Hermetic: fake LLM (`GenericFakeChatModel`-style scripted tool
caller via the `get_llm` seam), `fakeredis.aioredis`, `AsyncQdrantClient(":memory:")`
with a fake embedder, stub Mem0, `MemorySaver`, `InMemoryUserStore`/
`InMemoryThreadStore` (no real Postgres for auth/thread logic either).
`tests/test_graph_routing.py` is the critical suite (default agent, handoff
chain, sticky, loop-guard refusal, per-turn reset, bridge pruning);
`tests/test_ordering_routing.py` extends it to instamart/dineout + the
provider-unavailable prompt swap. `tests/test_hitl.py` covers
interrupt/approve/edit/reject on a real gated tool (`open_mac_app`, with
`subprocess.run` patched). `tests/test_planner_routing.py` covers the planner
composing into the swarm. Newer suites: `test_llm_registry` /
`test_resilient_middleware` (providers, slots, cooldown/fallback),
`test_mcp_providers` (guarded tools, staleness, hot reload, tracker
whitelist), `test_system_api` (status/metrics/JWT autogen/events cap),
`test_time_travel` (checkpoint listing + forking), `test_headroom`
(summarization config, progress, guardian verdict, research subagent). No test
uses FastAPI's `TestClient` — routes are exercised by unit-testing their
dependencies/helpers directly (e.g. `get_user_id`, `read_graph_messages`).

Frontend gate: `cd web && npm run build && npx oxlint && npm run test` —
Vitest + React Testing Library cover the SSE parser (split-chunk buffering,
additive unknown keys, checkpoint_id), InterruptCard decision collection, and
the theme store.
