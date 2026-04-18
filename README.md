# SubAgents — Perceptual AI Assistant

A local AI assistant that watches your camera, builds a structured world model
of what it sees, and answers questions about the environment accurately and efficiently.

Built on **LangGraph**, **Ollama**, and **FastAPI**. Runs entirely offline on a laptop.

---

## What it does

- **Watches your camera** continuously via WebSocket
- **Detects motion** cheaply (OpenCV pixel diff, ~1ms, no model)
- **Understands the scene** using moondream (fast 1.6B VLM, every 20s on motion)
- **Maintains a World Model** — structured current state: who's there, what objects, what activity
- **Remembers 5 minutes** of observations as a timestamped text log
- **Indexes frames with YOLO** — finds the most relevant historical frame for visual queries
- **Answers questions** using the most efficient path: world model → text log → live frame

---

## Quick Start

### 1. Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | |
| [Ollama](https://ollama.ai) | Local model server |
| `moondream` model | Fast scene understanding (1.6B, ~2-5s) |
| `gemma4` model | Chat / reasoning model |

```bash
ollama pull moondream   # primary vision model (~1.6GB)
ollama pull gemma4      # chat model
```

**Optional — for smart frame search:**
```bash
uv add ultralytics      # YOLO object detection (~6MB model auto-downloads)
```

**Optional — LLaVA for higher accuracy visual queries:**
```bash
ollama pull llava       # 7B vision model, slower but more accurate
# Then set in .env: VISION_MODEL=llava
```

### 2. Install dependencies

```bash
cd SubAgents
uv sync
```

### 3. Configure `.env`

```env
# Ollama on this machine
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Optional: use a separate machine for vision (avoids competing with chat model)
# OLLAMA_VISION_URL=http://192.168.1.22:11434

# Optional: switch vision model (default: moondream)
# VISION_MODEL=llava

# Optional: enable BLIP base captioning for richer frame search
# ENABLE_BLIP=true
```

### 4. Start

```bash
langgraph dev
```

- **Chat UI:** `http://127.0.0.1:2024`
- **Studio:** `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`
- **API Docs:** `http://127.0.0.1:2024/docs`

### 5. Use it

1. Open the chat UI
2. Enter your Bearer token
3. Click the **camera button**
4. Ask questions:

| Question | Tool used | Speed |
|---|---|---|
| `"who is in the room?"` | `recall_world` | Instant |
| `"what is on the desk?"` | `recall_world` | Instant |
| `"what happened in the last 5 minutes?"` | `recall_recent` | Instant |
| `"how many buttons on his shirt?"` | `recall_world` → `look_now` | 2-5s |
| `"read the text on that whiteboard"` | `look_now` | 5-30s |

---

## Architecture

```
Browser (webcam)
    │  frame every 2s (WebSocket)
    ▼
webapp.py
    ├── frame_buffer      every frame, 5-min rolling ring buffer
    └── perception_loop
          │  motion detected?
          ├─ YOLO (every 15s, CPU, ~100ms)
          │    → frame_store (frame + object tags for smart search)
          │
          └─ moondream (every 20s, Ollama, 2-5s)
               Structured prompt → CAPTION / PEOPLE / OBJECTS / ACTIVITY / ENVIRONMENT
               ├─ event_log    (timestamped text history, 5 min)
               └─ world_model  (current structured state, always latest)

User asks a question → supervisor agent (gemma4)
    │
    ├─ 1. recall_world   → world_model    (instant, answers most questions)
    ├─ 2. recall_recent  → event_log      (instant, for history questions)
    └─ 3. look_now       → frame_store.search() + moondream/LLaVA  (2-30s)
```

### How questions get answered

| Question type | Example | Tool | Why |
|---|---|---|---|
| Current state | "who is there?" | `recall_world` | World model has structured person/object info |
| History | "what happened?" | `recall_recent` | Text log has timestamped events |
| Fine detail | "how many buttons?" | `recall_world` → `look_now` | World model first; frame if needed |
| Real-time | "what am I doing now?" | `look_now` | User wants freshness |
| Text reading | "what does sign say?" | `look_now` | Requires pixel-level accuracy |

---

## Project Structure

```
SubAgents/
├── src/
│   ├── core/
│   │   └── world_model.py             # Structured current-state model (People/Objects/Activity)
│   ├── agents/
│   │   └── supervisor_agent.py        # LangGraph ReAct agent (gemma4 + 3 tools)
│   ├── tools/
│   │   ├── world_tools.py             # recall_world  — reads world_model (instant)
│   │   ├── memory_tools.py            # recall_recent — reads event_log  (instant)
│   │   └── vision_tools.py            # look_now      — live frame + VLM (2-30s)
│   ├── utils/
│   │   ├── frame_buffer.py            # Raw frame ring buffer (every frame, 5 min)
│   │   ├── event_log.py               # Timestamped text observation log (5 min)
│   │   ├── frame_store.py             # YOLO-tagged motion frames + search()
│   │   ├── perception_loop.py         # Motion gate → YOLO + moondream paths
│   │   ├── yolo_detector.py           # YOLOv8n lazy loader (optional)
│   │   ├── blip_captioner.py          # BLIP lazy loader (optional, ENABLE_BLIP=true)
│   │   ├── summarization_pipeline.py  # Disabled stub
│   │   └── memory_store.py            # Disabled stub
│   ├── llm_config.py                  # LLM setup (gemma4 via Ollama)
│   └── webapp.py                      # FastAPI + WebSocket handler
├── static/
│   └── index.html                     # Self-contained chat UI
├── langgraph.json
├── pyproject.toml
└── .env
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Chat UI |
| `POST` | `/chat?thread_id=<id>` | Send message, receive AI response |
| `WS` | `/ws/frames?thread_id=<id>` | Stream camera frames |
| `GET` | `/health` | Health check |
| `GET` | `/history/{thread_id}` | Conversation history |

---

## Configuration

### `.env` variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama for gemma4 (chat) |
| `OLLAMA_VISION_URL` | same as above | Ollama for vision model — set to Mac Mini to avoid contention |
| `VISION_MODEL` | `moondream` | Vision model name (`moondream`, `llava`, `phi3.5-vision`) |
| `ENABLE_BLIP` | `false` | Enable BLIP base captioning for richer frame search |

### Tuning (`src/utils/perception_loop.py`)

| Constant | Default | Description |
|---|---|---|
| `_CAPTION_COOLDOWN` | `20s` | moondream caption interval (was 90s with LLaVA) |
| `_YOLO_COOLDOWN` | `15s` | YOLO detection interval |
| `_MOTION_THRESHOLD` | `2.5` | Pixel diff sensitivity (lower = more sensitive) |
| `_CAPTION_MODEL` | `moondream` | Override with `VISION_MODEL` env var |

---

## Performance Notes

| Component | RAM | Inference | Notes |
|---|---|---|---|
| moondream (Ollama) | ~1.5GB | 2-5s | Primary captioner, every 20s |
| gemma4 (Ollama) | ~4GB | 3-10s | Chat reasoning |
| YOLOv8n | ~50MB | ~100ms | Optional, CPU-only |
| BLIP base | ~900MB | ~2s | Optional, `ENABLE_BLIP=true` |
| LLaVA (optional) | ~4GB | 30-60s | Use via `VISION_MODEL=llava` for max accuracy |

**Key laptop optimisations:**
- moondream replaces LLaVA for background captioning (10× faster → denser memory)
- YOLO and moondream run in separate executors (YOLO never waits for Ollama)
- Semaphore ensures only 1 Ollama vision call at a time
- Frame processing offloaded from async event loop to thread pool
- World model answers most questions instantly without any model call

---

## Future Roadmap

```
Now      MacBook POC    moondream + world model + LangGraph
         ↓
Next     Add Mac Mini   OLLAMA_VISION_URL → separate machine, no contention
         ↓
Later    Edge devices   Pi5 (sensor node) + Jetson (perception) + Mac Mini (reasoning)
         ↓
Future   ROS2           Each node becomes a ROS node, transport swaps to DDS
                        cmd_vel, robot arms, spatial navigation
```

The backend interface pattern (`VLMBackend`, `DetectorBackend`) is designed so
switching from Ollama to llama.cpp (for Pi5/Jetson) requires only a config change.
