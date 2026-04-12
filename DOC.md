# SubAgents — Project Documentation

Detailed technical reference for every file, the data flow, and design decisions.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Data Flow — Frame Ingestion](#2-data-flow--frame-ingestion)
3. [Data Flow — Chat Query](#3-data-flow--chat-query)
4. [File Reference](#4-file-reference)
5. [LLaVA Semaphore — Why It Exists](#5-llava-semaphore--why-it-exists)
6. [Disabled Components](#6-disabled-components)
7. [Browser UI](#7-browser-ui)
8. [Common Questions](#8-common-questions)

---

## 1. System Overview

The system has two independent pipelines that share storage:

**Pipeline A — Passive observation (always running while camera is on)**
```
Browser webcam → WebSocket → frame_buffer (raw pixels)
                           → perception_loop → motion? → LLaVA → event_log (text)
```

**Pipeline B — Active response (triggered by user chat)**
```
User message → LangGraph supervisor (gemma4)
                    → recall_recent tool → event_log (text, fast)
                    → look_now tool     → frame_buffer + LLaVA (slower)
```

Both pipelines share `frame_buffer` and `event_log`. There is no database — everything lives in RAM and is evicted after 5 minutes.

---

## 2. Data Flow — Frame Ingestion

```
Browser
  │
  │  captureCanvas.toDataURL("image/jpeg", 0.6)
  │  → base64 string  (typically 20-50 KB)
  │  sent every 2 seconds via WebSocket
  │
  ▼
webapp.py  →  video_frame_ws()  [async WebSocket handler]
  │
  │  offloads to _frame_executor thread so async loop stays free
  │
  ▼  (in thread)
_process_frame(data):
  │
  ├─ store_frame(tid, data)
  │     └── frame_buffer.py
  │           Appends (now, b64) to a deque for this thread_id.
  │           Evicts any entry older than 300 seconds (5 min).
  │           Result: deque holds ~150 frames max at 2s intervals.
  │
  └─ perception.on_frame(tid, data)
        └── perception_loop.py
              │
              ├─ _decode_to_gray(b64)
              │     Decodes JPEG → grayscale numpy array
              │     Resizes to 160×120 (tiny, fast for diff)
              │
              ├─ _detect_motion(thread_id, gray)
              │     Compares to previous frame using numpy absdiff
              │     mean(diff) > 2.5 → motion = True
              │     Stores current frame as next "previous"
              │
              └─ _maybe_caption(thread_id, b64)  [only on motion]
                    │
                    ├─ Check per-thread cooldown (90s)
                    │     If < 90s since last caption → skip
                    │
                    ├─ Check global semaphore (non-blocking acquire)
                    │     If LLaVA already running → skip
                    │     (prevents flooding Ollama with queued calls)
                    │
                    └─ Submit _caption_frame_async to thread pool
                          │
                          ▼  (in background thread)
                          POST http://ollama/api/generate
                          model: llava
                          prompt: "Describe this scene in 2-3 sentences..."
                          images: [b64]
                          timeout: 60s
                          │
                          ├─ Success → event_log.log(tid, caption)
                          │     Stores Event(id, timestamp, description, thread_id)
                          │     Eviction: events older than 300s dropped automatically
                          │
                          └─ Finally → _caption_semaphore.release()
                                (always released, even on timeout)
```

---

## 3. Data Flow — Chat Query

```
Browser
  │
  │  POST /chat  body: { query: "what color is my shirt?" }
  │              header: Authorization: Bearer <token>
  │
  ▼
webapp.py  →  chat()
  │
  ├─ Ensure thread exists in LangGraph Server
  │
  └─ client.runs.wait(thread_id, assistant_id="agent", input={messages})
        │
        ▼
supervisor_agent.py  →  supervisor_node()
  │
  │  Prepends SYSTEM_PROMPT to message list:
  │    "Try recall_recent first. Only call look_now for real-time detail."
  │
  │  Calls gemma4 via Ollama (localhost:11434/api/chat)
  │
  ├── gemma4 decides: answer directly, or call a tool?
  │
  ├─ Option A: call recall_recent
  │     memory_tools.py → recall_recent()
  │       event_log.get_recent_events(tid, seconds=300)
  │       format: "[45s ago] A person in a blue shirt..."
  │       Returns text. No LLaVA. Instant.
  │
  ├─ Option B: call look_now
  │     vision_tools.py → look_now()
  │       _caption_semaphore.acquire()  ← waits if caption running
  │       frame_buffer.get_latest_frames(tid, count=1)
  │       POST ollama/api/generate  model=llava  prompt=query  images=[frame]
  │       timeout: 120s
  │       Returns LLaVA answer.
  │       _caption_semaphore.release()
  │
  └─ gemma4 receives tool result → generates final answer
        │
        ▼
webapp.py  →  _extract_response(result)
  Finds the last AI message with content and no pending tool_calls.
  Returns it as the chat response.
```

---

## 4. File Reference

### `src/webapp.py`

**Role:** FastAPI server + entry point for all HTTP and WebSocket traffic.

**Key parts:**

| Component | Purpose |
|---|---|
| `lifespan()` | Startup/shutdown hook. Currently just logs. |
| `POST /chat` | Receives user query, calls LangGraph SDK, returns AI response. |
| `WS /ws/frames` | Receives base64 JPEG frames from browser every 2s. Offloads processing to `_frame_executor` thread. |
| `_frame_executor` | `ThreadPoolExecutor(max_workers=1)` — keeps async event loop free during frame processing. |
| `_extract_response()` | Walks the LangGraph message list backwards to find the last AI text response (skips tool call messages). |
| `_ensure_thread()` | Creates the LangGraph thread if it doesn't exist yet. |

---

### `src/utils/frame_buffer.py`

**Role:** 5-minute rolling buffer of raw camera frames.

**Storage:** `dict[thread_id → deque[(timestamp, b64_jpeg)]]` in RAM.

**Key functions:**

| Function | What it does |
|---|---|
| `store_frame(tid, b64)` | Appends frame, evicts entries older than 300s. |
| `get_latest_frames(tid, count)` | Returns the `count` most recent frames. |
| `get_frames_last_n_seconds(tid, seconds)` | Returns all frames within the last N seconds. |
| `get_frames_in_range(tid, start, end)` | Returns frames within a unix timestamp range. |

**Memory usage:** At 2s interval, 300s window → ~150 frames. At 30KB/frame (60% JPEG quality) → ~4.5MB max per thread.

---

### `src/utils/event_log.py`

**Role:** 5-minute rolling log of LLaVA text descriptions (one per motion event).

**Storage:** `dict[thread_id → list[Event]]` in RAM. Each `Event` has: `id`, `timestamp`, `description`, `thread_id`, `tags`.

**Key functions:**

| Function | What it does |
|---|---|
| `log(tid, description, tags)` | Adds a new event with current timestamp. |
| `get_recent_events(tid, seconds)` | Returns events from the last N seconds. |
| `format_for_llm(events)` | Formats events as `"[45s ago] description..."` for LLM context. |
| `format_recent_for_llm(tid, seconds)` | Convenience: get + format in one call. |
| `evict_expired()` | Removes events older than 3 hours (called on write). |

**Retention:** Raw events kept for 3 hours in memory (but only the last 5 min is ever shown to the LLM).

---

### `src/utils/perception_loop.py`

**Role:** Motion detection gate + async LLaVA captioning trigger.

**Key constants:**

| Constant | Value | Meaning |
|---|---|---|
| `_MOTION_THRESHOLD` | `2.5` | Mean pixel diff (0-255 scale) to classify as motion |
| `_CAPTION_COOLDOWN` | `90s` | Minimum gap between LLaVA calls per thread |
| `_caption_semaphore` | `Semaphore(1)` | Global — only 1 LLaVA call at a time across all threads |

**Motion detection:**
- Resizes frame to 160×120 grayscale
- Computes `mean(abs(current - previous))`
- If > 2.5 → motion. Fast — pure numpy, no model.

**Caption dispatch:**
1. Check per-thread 90s cooldown
2. Try non-blocking semaphore acquire — skip if LLaVA busy
3. Update timestamp, submit to thread pool
4. `_caption_frame_async` sends frame to LLaVA, writes result to `event_log`, releases semaphore in `finally`

**Caption prompt:**
> "Describe this scene in 2-3 sentences. Cover: (1) what people are doing and their appearance (clothing colors, position), (2) notable objects visible and where they are, (3) the setting or environment."

More detail in captions = more questions answerable from text alone (no LLaVA re-call needed).

---

### `src/tools/memory_tools.py`

**Role:** `recall_recent` LangGraph tool — reads the text event log.

**When the agent calls it:** Past/historical questions. "What happened", "was there X", "what did you see earlier".

**What it returns:**
```
Observations from the last 5 minutes (4 captured):

[45s ago] A person in a blue shirt is sitting at a desk, typing...
[2m ago] The person stood and walked toward a window...
[3m ago] ...
```

**Cost:** Sub-millisecond. No model calls. Pure RAM read.

---

### `src/tools/vision_tools.py`

**Role:** `look_now` LangGraph tool — grabs a live camera frame and asks LLaVA a specific question.

**When the agent calls it:** Current-state questions. "What am I doing right now", "what color is X", "how many people", "describe the scene".

**Semaphore behaviour:**
- Acquires `_caption_semaphore` with `blocking=True`
- If background caption is running → waits for it to finish first
- Then runs its own LLaVA call
- Releases semaphore in `finally`

**Timeout:** 120 seconds (user-adjusted — LLaVA first call can be slow while model loads).

---

### `src/agents/supervisor_agent.py`

**Role:** Main LangGraph ReAct agent. Receives user message, decides which tools to call, synthesizes final response.

**LLM:** `gemma4:latest` via `ChatOllama` (localhost:11434).

**Tools bound:** `[recall_recent, look_now]`

**System prompt teaches the routing rule:**
- Try `recall_recent` first (fast, no model call)
- Only call `look_now` when the text log doesn't contain the specific detail
- Never call both for the same question unless the first is genuinely insufficient
- For "right now" / "currently" questions → prefer `look_now`

**Graph structure:**
```
supervisor_node ──(tool_calls)──► tools ──► supervisor_node
                └─(no tools)───► END
```

---

### `src/llm_config.py`

**Role:** LLM initialization.

**Current setup:**
- Chat model: `gemma4:latest` via `ChatOllama` at `localhost:11434`
- Vision model: `llava` via `requests.post` to `OLLAMA_BASE_URL` (or `OLLAMA_VISION_URL`)

**OpenAI alternative (commented out):** The file has commented-out OpenAI config. To switch to OpenAI (much faster chat responses):
```python
from langchain.chat_models import init_chat_model
llm = init_chat_model("gpt-4o-mini", temperature=0)
```
Requires `OPENAI_API_KEY` in `.env`.

---

### `src/utils/frame_store.py`

**Role:** No-op delegate to `frame_buffer`. Exists only so imports don't break.

The original implementation ran CLIP (PyTorch + open_clip) to compute 512-dim embeddings on every motion-triggered frame. This used 1-2GB RAM and caused slow startup. Replaced with a thin wrapper that just calls `frame_buffer` functions.

**CLIP is fully removed.** Do not install `torch` or `open-clip-torch`.

---

### `src/utils/summarization_pipeline.py` and `src/utils/memory_store.py`

**Role:** Disabled no-op stubs.

The original design had a rolling summarization hierarchy:
```
raw events → 5-min summary → 10-min → 30-min → 1hr → 12hr → daily
```
A background thread woke every 30 seconds and called the LLM to produce summaries at each level. This caused:
- Background LLM calls competing with chat requests
- ~50-second chat response times
- Constant timeout warnings in logs

Both files are now stubs with empty method bodies. All interfaces are preserved so the rest of the code continues to import from them without errors.

---

## 5. LLaVA Semaphore — Why It Exists

Ollama runs one model at a time on a single machine. If two LLaVA calls are in progress simultaneously:
- Ollama queues the second one internally
- Both calls take longer
- Background captions delay user responses and vice versa

The `_caption_semaphore = threading.Semaphore(1)` in `perception_loop.py` is imported by `vision_tools.py`. Both use the same semaphore object:

| Caller | Acquire mode | Behaviour |
|---|---|---|
| `perception_loop._maybe_caption` | `blocking=False` | Skip if busy — background captions are optional |
| `vision_tools.look_now` | `blocking=True` | Wait if busy — user request must complete |

This means:
- Background captions never block each other or the user
- User's `look_now` call may wait briefly if a background caption just started (max 60s wait)
- Ollama only ever handles one LLaVA request at a time

---

## 6. Disabled Components

| Component | File | Why disabled |
|---|---|---|
| CLIP semantic search | `frame_store.py` | Requires PyTorch + open_clip (~1-2GB RAM, slow on laptop) |
| Summarization hierarchy | `summarization_pipeline.py` | Background LLM calls every 30s blocked chat responses |
| MemoryStore (hierarchy tree) | `memory_store.py` | No longer needed without summarization pipeline |

All three are preserved as stubs (not deleted) so their imports don't cause errors.

---

## 7. Browser UI

**File:** `static/index.html` — fully self-contained, no build step.

**Layout:**
- Left panel: camera feed + tools panel (placeholder)
- Right panel: chat interface

**Camera flow:**
1. User clicks camera button → `getUserMedia({ video: { width: 640, height: 480 } })`
2. WebSocket connects to `/ws/frames?thread_id=<current_thread>`
3. Every 2 seconds: canvas captures frame at 60% JPEG quality, sends base64 string via WebSocket
4. When thread changes (new chat): WebSocket reconnects with new thread_id

**Chat flow:**
1. User types → `POST /chat?thread_id=<id>` with `Authorization: Bearer <token>`
2. Shows typing indicator while waiting
3. Renders response as Markdown (using `marked.js` + `DOMPurify`)

**Token:** The Bearer token is stored in `localStorage` so it persists across page refreshes.

---

## 8. Common Questions

**Q: Why is the first LLaVA call slow (45+ seconds)?**
LLaVA needs to be loaded into VRAM/RAM on first use. Subsequent calls (while the model stays loaded) are 10-20s. The 90s cooldown means the model has time to stay warm between background captions.

**Q: Why does the chat take a long time even without vision?**
Both `gemma4` (chat) and `llava` (captions) share the same Ollama instance. If a background caption is running when you send a chat message, Ollama queues your request. Fix: set `OLLAMA_VISION_URL` to a second machine.

**Q: Why does the log say "12 changes detected" every 10 seconds?**
That is `watchfiles` (LangGraph dev mode) watching your source files for hot-reload. Normal behaviour — not a problem.

**Q: How do I make it more sensitive to motion?**
Lower `_MOTION_THRESHOLD` in `perception_loop.py` from `2.5` to `1.5`. Careful — a stable but noisy camera (lighting flicker) can trigger captions constantly.

**Q: How do I get faster answers?**
Switch the supervisor LLM to OpenAI in `llm_config.py`. `gpt-4o-mini` responds in 1-3 seconds vs 30-60s for a local gemma4.

**Q: Can I add more tools?**
Yes. Create a function decorated with `@tool` in `src/tools/`, import it in `src/tools/__init__.py`, and add it to `ALL_TOOLS`. The supervisor will automatically use it.
