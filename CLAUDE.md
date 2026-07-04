# CLAUDE.md — Developer & AI Reference

Technical reference for the SubAgents codebase. Read this before making changes.

---

## Quick Facts

- **Runtime**: Python 3.11+, managed with `uv`
- **Framework**: LangGraph + `langgraph-swarm` (graph), LangChain agents,
  FastAPI (standalone API), Ollama/llama.cpp/OpenAI (LLM)
- **Start command**: `uv run uvicorn main:app --port 2024` (no more `langgraph dev`)
- **Entry**: `main.py` → `src/app.py:create_app()`; graph built in the lifespan
- **3 agents**: conversation (default/router), swiggy, tracker — coordinated as a swarm
- **Stores**: Postgres (checkpoints), Redis (frames/cache/rate-limit), Qdrant (RAG + Mem0)

---

## Folder Structure

```
main.py                  # uvicorn entry (app = create_app())
docker-compose.yml       # postgres, redis, qdrant
src/
├── app.py               # FastAPI factory + lifespan (owns all long-lived resources)
├── api/                 # chat, frames, uploads, events, auth, deps
├── graph/               # state, handoff, swarm, build (parent graph)
├── memory/              # mem0_client, recall, post_turn, history_index
├── rag/                 # qdrant, embeddings, store, ingestion, retrieval_tools, web_cache
├── services/            # redis_client, frame_buffer, rate_limit, tts
├── tools/               # vision_tools, system_tools, swiggy_mcp, __init__ (tool sets)
├── prompts/             # conversation, swiggy, tracker (build_prompt() -> str)
├── commons/constants.py # agent name strings + AGENT_DESCRIPTIONS
├── models/schema.py     # pydantic request/response
└── configs/             # settings.py (pydantic-settings), llm.py, logging_config.py
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
5. `load_swiggy_tools()` (async) → `apply_swiggy_tools(...)` — **no import-time
   network calls** (fixed the old `asyncio.run()` antipattern)
6. `build_graph(checkpointer, mem0)` — must run AFTER `apply_swiggy_tools`
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

- Agents built with `create_agent(model, tools, middleware=[...], state_schema=VisualAgentState, name=...)`.
- Two middlewares per agent:
  - `dynamic_prompt` — appends recalled memories to the base prompt.
  - `KeepOnlyLatestBridge` (subclass of `AgentMiddleware`, implements **both**
    `wrap_model_call` and `awrap_model_call`) — prunes stale handoff bridges.
- `create_swarm([conversation, swiggy, tracker], default_active_agent="conversation",
  state_schema=VisualAssistantState)`.

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
the extra channels for the react subgraphs.

---

## Streaming (`src/api/chat.py`)

`graph.astream(inputs, config, stream_mode=["messages","updates"], subgraphs=True)`:
- Emit `{"delta": text}` for `AIMessage` chunks with content and **no tool
  calls** (filters tool/handoff chunks and tool-node output).
- Track `active_agent` from `updates` payloads (explicit set, else agent node name).
- On completion: `{"done", thread_id, active_agent}`; on error/timeout: `{"error"}`.
- Wrapped in `asyncio.timeout(settings.chat_timeout_seconds)`.
- **Frontend contract**: `static/index.html` appends `parsed.delta` raw and
  buffers partial SSE lines. Do not switch tokens back to a `text` field — the
  old code joined `text` events with `\n`, which corrupts token streaming.

Post-turn work is a **FastAPI `BackgroundTasks`** task (not a bare
`asyncio.create_task`, which gets GC'd/cancelled under StreamingResponse).

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
(openai=1536, ollama=768) unless `EMBEDDING_DIM` overrides. Tests call
`get_settings.cache_clear()` around env monkeypatches.

---

## Tools (`src/tools/__init__.py`)

```python
CONVERSATION_TOOLS = [capture_webcam, get_system_info, open_mac_app,
                      search_documents, recall_history, *web_tools]
SWIGGY_TOOLS  = []   # filled by apply_swiggy_tools() at startup
TRACKER_TOOLS = []   # filled by apply_swiggy_tools() at startup
```

- Handoff tools are appended per-agent in `swarm.py`, not stored here.
- `apply_swiggy_tools(mcp_tools)` mutates the lists in place; the graph is built
  after it so ToolNodes snapshot the full lists.
- `capture_webcam` is **async** (reads the Redis frame buffer).

---

## Adding a New Agent

1. `src/prompts/{name}.py` with `build_prompt() -> str`.
2. Add the name constant + `AGENT_DESCRIPTIONS` entry in `src/commons/constants.py`.
3. Add a `{NAME}_TOOLS` list in `src/tools/__init__.py`.
4. In `src/graph/swarm.py`: build the agent with `_make_agent(...)`, give it the
   appropriate `transfer_to_*` handoff tools, add it to `create_swarm([...])`,
   and add `transfer_to_<newname>` to the other agents that should reach it.
5. Update the other agents' prompts with routing rules for the new agent.

---

## Common Pitfalls

- **Invoke the graph async** — `recall_memories` is async-only; sync `invoke`
  raises. Tests use `ainvoke`.
- **Build the graph after `apply_swiggy_tools`** — otherwise swiggy/tracker have
  no MCP tools.
- **Middleware must implement both sync and async** `wrap_model_call` /
  `awrap_model_call` (we call `astream`).
- **Don't revive the `text` SSE field for tokens** — use `delta` (frontend
  joins `text` with newlines).
- **Embedding-dim invariant** — switching `EMBEDDING_PROVIDER` requires dropping
  Qdrant collections; startup asserts the sizes match.
- **Mem0 on local models** — extraction hallucinates; keep `MEM0_LLM_PROVIDER=openai`.
- **Loop guard** — >3 handoffs to one agent per turn is refused (not rerouted);
  `agent_turn_visits` resets via the `{}` passed in each `/chat` input.

---

## Tests

`uv run pytest`. Hermetic: fake LLM (`GenericFakeChatModel`-style scripted tool
caller via the `get_llm` seam), `fakeredis.aioredis`, `AsyncQdrantClient(":memory:")`
with a fake embedder, stub Mem0, `MemorySaver`. `tests/test_graph_routing.py` is
the critical suite (default agent, handoff chain, sticky, loop-guard refusal,
per-turn reset, bridge pruning).
