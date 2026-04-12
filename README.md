# SubAgents
1.install uv in system
2.in terminal, run "uv sync" to install dependencies
3.in terminal, run "langgraph dev" to start the server
4.add .evn tool file in root directory, and add the following content:
```

Then you will get three endoints:
- 🚀 Custom UI Endpoint: http://127.0.0.1:2024
![img.png](img.png)

- 🎨 Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- 📚 API Docs: http://127.0.0.1:2024/docs

-----------

# SubAgents — Perceptual AI Assistant

A local AI assistant that watches your camera, builds a 5-minute rolling memory of what it sees, and answers questions about the environment in real time.

Built on **LangGraph**, **Ollama**, and **FastAPI**.

---

## What it does

- **Watches your camera** continuously via WebSocket
- **Detects motion** cheaply (OpenCV pixel diff — no model required, ~1ms per frame)
- **Describes what it sees** using LLaVA (local vision model via Ollama), triggered on motion
- **Remembers the last 5 minutes** of observations as timestamped text descriptions
- **Answers questions** by reading from memory first (fast), falling back to a live camera frame only when the text log isn't enough

---

## Quick Start

### 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | |
| [Ollama](https://ollama.ai) | Local model server |
| `gemma4` model | Chat / reasoning model |
| `llava` model | Vision model for camera analysis |

Pull the required models:
```bash
ollama pull gemma4
ollama pull llava
```

### 2. Install dependencies

```bash
cd SubAgents
uv sync
```

> Do **NOT** install the `[clip]` optional extra (`torch`, `open-clip-torch`). It is disabled and will cause high RAM usage on a laptop.

### 3. Configure

Create a `.env` file in the project root:

```env
# Ollama instance for the chat model (gemma4)
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Optional — route LLaVA to a separate machine so it doesn't compete with gemma4
# OLLAMA_VISION_URL=http://192.168.1.22:11434
```

### 4. Start the server

```bash
langgraph dev
```

You will get three endpoints:

- **Chat UI:** `http://127.0.0.1:2024`
- **LangGraph Studio:** `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`
- **API Docs:** `http://127.0.0.1:2024/docs`

### 5. Use it

1. Open `http://127.0.0.1:2024` in your browser
2. Enter your Bearer token in the settings bar
3. Click the **camera button** to enable your webcam
4. Start asking questions:

| Question | What happens internally |
|---|---|
| `"what happened in the last 5 minutes?"` | Reads text memory — instant |
| `"was anyone in the room?"` | Reads text memory — instant |
| `"what color is my shirt?"` | Checks text memory; falls back to live frame if needed |
| `"what am I doing right now?"` | Grabs live frame → asks LLaVA (30-60s) |
| `"describe the current scene"` | Grabs live frame → asks LLaVA (30-60s) |

---

## Architecture

```
Browser (webcam enabled)
    │
    │  base64 JPEG frame every 2 seconds  (WebSocket /ws/frames)
    ▼
webapp.py  ──────────────────────────────────────────
    │
    ├─ frame_buffer.py
    │     Stores EVERY frame in a 5-min rolling deque.
    │     ~150 frames × 30KB = ~4MB RAM max.
    │
    └─ perception_loop.py
          Motion detection (numpy diff on 160×120 gray image, ~1ms)
          If motion AND cooldown elapsed AND LLaVA not busy:
              → send frame to LLaVA (Ollama) in background thread
              → write caption to event_log.py

event_log.py
    Stores timestamped text descriptions (LLaVA captions) for the last 5 min.
    "[45s ago] A person in a blue shirt is typing at a laptop..."

─────────────────────────────────────────────────────

User sends a chat message  →  POST /chat
    │
    ▼
supervisor_agent.py  (gemma4 via Ollama)
    System prompt: "Try recall_recent first. Only call look_now for real-time detail."
    │
    ├─ recall_recent  (memory_tools.py)
    │     Reads event_log text — sub-millisecond. No LLaVA call.
    │     Use for: "what happened", "was there X", "what did you see"
    │
    └─ look_now  (vision_tools.py)
          Grabs latest frame from frame_buffer.
          Sends to LLaVA with user's specific question.
          Use for: "right now", colors, counts, live detail.
          Shares semaphore with perception_loop so only 1 LLaVA call at a time.
```

---

## Project Structure

```
SubAgents/
├── src/
│   ├── agents/
│   │   ├── supervisor_agent.py        # Main LangGraph ReAct agent
│   │   └── video_analysis_agent.py    # Alternate graph (same tools)
│   ├── tools/
│   │   ├── vision_tools.py            # look_now — live frame → LLaVA
│   │   └── memory_tools.py            # recall_recent — text log (fast)
│   ├── utils/
│   │   ├── frame_buffer.py            # 5-min rolling raw frame store
│   │   ├── event_log.py               # 5-min rolling text description store
│   │   ├── perception_loop.py         # Motion gate + LLaVA background captioning
│   │   ├── frame_store.py             # No-op delegate to frame_buffer (CLIP removed)
│   │   ├── summarization_pipeline.py  # Disabled stub (was 6-level LLM hierarchy)
│   │   └── memory_store.py            # Disabled stub (was hierarchical memory tree)
│   ├── configs/
│   ├── models/
│   ├── states/
│   ├── auth/
│   ├── llm_config.py                  # LLM setup (gemma4 via Ollama)
│   └── webapp.py                      # FastAPI server + WebSocket handler
├── static/
│   └── index.html                     # Self-contained chat UI
├── langgraph.json                     # LangGraph graph config
├── pyproject.toml
└── .env                               # Local config (not committed)
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI (HTML) |
| `POST` | `/chat?thread_id=<id>` | Send message, receive AI response |
| `WS` | `/ws/frames?thread_id=<id>` | Stream camera frames from browser |
| `GET` | `/health` | Health check |
| `GET` | `/history/{thread_id}` | Conversation history for a thread |

---

## Configuration Reference

### `.env` variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama for gemma4 (chat model) |
| `OLLAMA_VISION_URL` | same as above | Ollama for LLaVA (vision). Set to a separate machine to eliminate contention. |

### Tuning parameters (`src/utils/perception_loop.py`)

| Parameter | Default | Description |
|---|---|---|
| `_CAPTION_COOLDOWN` | `90s` | Minimum seconds between LLaVA caption attempts. Raise if Ollama is still slow. |
| `_MOTION_THRESHOLD` | `2.5` | Mean pixel diff to classify as motion. Lower = more sensitive. |

---

## Performance Notes

This system is designed to run entirely on a laptop with a single Ollama instance.

**What was removed from the original design:**
- CLIP semantic search (PyTorch + open_clip — 1-2GB RAM, disabled)
- 6-level summarization hierarchy (5min→10min→30min→1hr→12hr→daily — background LLM calls, disabled)

**Key laptop optimizations:**
- 1 LLaVA call at a time (global semaphore — no flooding)
- 90s cooldown so LLaVA finishes before the next attempt
- Motion detection on 160×120 image (not full resolution)
- Frame processing offloaded to a thread (async event loop never blocked)

**Best setup for performance:** Run LLaVA on a Mac Mini or second machine and set `OLLAMA_VISION_URL`. This way `gemma4` and `llava` never share the same Ollama instance.

