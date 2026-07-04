# Memory & RAG

The assistant has four kinds of memory, all vector-backed by Qdrant:

| Layer | Collection | Scope | Written | Read |
|---|---|---|---|---|
| Long-term facts (Mem0) | `mem0_memories` | per user | post-turn | `recall_memories` node (every turn) |
| Conversation history | `history` (kind=turn) | per user | post-turn summary | `recall_history` tool |
| Vision history | `history` (kind=frame) | per user | post-turn | `recall_history` tool |
| Documents | `documents` | per user | `POST /upload` | `search_documents` tool |
| Web-search cache | `search_cache` | shared | on Tavily call | `cached_web_search` tool |

Plus **short-term** conversation state in Postgres (LangGraph checkpoints).

## Mem0 (long-term memory)

`src/memory/mem0_client.py` builds an `AsyncMemory` with Qdrant as the vector
store. Configuration is driven by settings:

- **Vector store**: Qdrant, collection `mem0_memories`, dim = `embedding_dim`.
- **Embedder**: follows `EMBEDDING_PROVIDER` (OpenAI or Ollama).
- **Extraction LLM**: `MEM0_LLM_PROVIDER` — **independent** of the chat model.
  Keep it on OpenAI `gpt-4o-mini`; local models hallucinate facts during
  extraction (empirically observed with small local models).

Read path: `recall_memories` (`src/memory/recall.py`) runs once per turn before
the swarm, searching Mem0 (`filters={"user_id": ...}`) and injecting hits into
`recalled_memories`. Write path: `run_post_turn` (`src/memory/post_turn.py`)
calls `mem0.add(...)` in a background task after the response is sent.

## RAG: document uploads

`POST /upload` → `src/rag/ingestion.py`:
extract text (PDF via `pypdf`, else utf-8) → `RecursiveCharacterTextSplitter`
(1000/150) → embed → upsert into `documents` with `{user_id, doc_id, filename,
chunk_index}`. The `search_documents` tool retrieves user-scoped chunks.

## RAG: conversation & vision history

`run_post_turn` → `src/memory/history_index.py`:

- **index_turn**: summarize the exchange with the utility LLM → upsert into
  `history` as `kind=turn`.
- **index_vision_frames**: if `capture_webcam` was used this turn, index a
  description into `history` as `kind=frame`. Modes (`VISION_INDEXING`):
  - `reuse` (default) — index the assistant's own visual answer (zero extra cost)
  - `llm` — re-describe the image with a multimodal call
  - `off` — skip

The `recall_history` tool answers "what did we talk about" / "what did I show
you last week" across threads.

## Web-search cache

`cached_web_search` (`src/rag/web_cache.py`) layers lookups:

1. **Redis exact-match** (`tavily:<sha256>`, TTL `WEB_CACHE_TTL_SECONDS`)
2. **Qdrant semantic** — near-duplicate query (score ≥ `WEB_CACHE_SCORE_THRESHOLD`,
   within `WEB_CACHE_SEMANTIC_MAX_AGE_SECONDS`)
3. **Live Tavily** — result written back to both layers

## ⚠️ Embedding dimension invariant

Every RAG collection and Mem0 are created with a fixed vector size derived from
`EMBEDDING_PROVIDER` (openai=1536, ollama=768). On startup `ensure_collections`
**fails fast** if an existing collection's size differs from the configured
provider. To switch providers:

```bash
# 1. stop the app
# 2. drop the affected collections (or reset all state)
docker compose down -v && docker compose up -d
# 3. set EMBEDDING_PROVIDER in .env, restart the app (collections re-create)
```

Uploaded documents and indexed history must be re-ingested after a switch.
