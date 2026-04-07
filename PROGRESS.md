# Implementation Progress

## Status Legend
- ✅ Done
- 🔄 In Progress
- ⏳ Planned
- ❌ Blocked

---

## Steps

### Step 1 — Memory Node + Store ✅
**Goal:** Core data structure for the hierarchical memory tree.

| Task | Status | File |
|------|--------|------|
| MemoryNode dataclass | ✅ | `src/utils/memory_store.py` |
| MemoryStore (thread-safe tree) | ✅ | `src/utils/memory_store.py` |
| Add/get/search/drill-down API | ✅ | `src/utils/memory_store.py` |

---

### Step 2 — Event Log (raw captions) ✅
**Goal:** Timestamped log of VLM captions from motion events. Foundation for all summaries.

| Task | Status | File |
|------|--------|------|
| Event dataclass | ✅ | `src/utils/event_log.py` |
| Thread-safe log store | ✅ | `src/utils/event_log.py` |
| Time-range retrieval | ✅ | `src/utils/event_log.py` |
| Formatted context output | ✅ | `src/utils/event_log.py` |
| `get_all_thread_ids()` public API | ✅ | `src/utils/event_log.py` |

---

### Step 3 — Rolling Summarization Pipeline ✅
**Goal:** Background jobs that compress raw events → 5min → 10min → 30min → 1hr → 12hr → daily.

| Task | Status | File |
|------|--------|------|
| Summarization scheduler | ✅ | `src/utils/summarization_pipeline.py` |
| 5-min summarizer (from raw events) | ✅ | `src/utils/summarization_pipeline.py` |
| 10-min summarizer | ✅ | `src/utils/summarization_pipeline.py` |
| 30-min summarizer | ✅ | `src/utils/summarization_pipeline.py` |
| 1-hr summarizer | ✅ | `src/utils/summarization_pipeline.py` |
| 12-hr summarizer | ✅ | `src/utils/summarization_pipeline.py` |
| Daily summarizer | ✅ | `src/utils/summarization_pipeline.py` |
| Watermark tracking per (thread, level) | ✅ | `src/utils/summarization_pipeline.py` |
| Wire into webapp lifespan startup | ✅ | `src/webapp.py` |
| Register thread on WebSocket connect | ✅ | `src/webapp.py` |

---

### Step 4 — Memory Query Tools ✅
**Goal:** LangGraph tools that let the agent query memory at the right level.

| Task | Status | File |
|------|--------|------|
| `recall_events` tool (text path, drill-down) | ✅ | `src/tools/memory_tools.py` |
| `visual_detail_query` tool (frame path) | ✅ | `src/tools/memory_tools.py` |
| Natural language time parser | ✅ | `src/tools/memory_tools.py` |
| Drill-down across all levels (not just first hit) | ✅ | `src/tools/memory_tools.py` |
| Register tools in `__init__.py` | ✅ | `src/tools/__init__.py` |

---

### Step 5 — Frame Store + CLIP + Perception Loop ✅
**Goal:** Keep compressed frames with CLIP embeddings; motion-gated VLM captioning in background.

| Task | Status | File |
|------|--------|------|
| Update frame_buffer.py with timestamps + `get_all_thread_ids()` | ✅ | `src/utils/frame_buffer.py` |
| FrameStore (compressed JPEG + CLIP embedding) | ✅ | `src/utils/frame_store.py` |
| CLIP embedding helper (lazy-load, optional) | ✅ | `src/utils/frame_store.py` |
| Semantic frame retrieval via cosine similarity | ✅ | `src/utils/frame_store.py` |
| Graceful fallback if CLIP not installed | ✅ | `src/utils/frame_store.py` |
| Motion gate (OpenCV absdiff, ~1ms) | ✅ | `src/utils/perception_loop.py` |
| Async VLM caption on motion → EventLog | ✅ | `src/utils/perception_loop.py` |
| Caption cooldown (5s) to avoid LLaVA flooding | ✅ | `src/utils/perception_loop.py` |
| `visual_detail_query` uses CLIP search first | ✅ | `src/tools/memory_tools.py` |
| Wire perception loop into WebSocket handler | ✅ | `src/webapp.py` |

---

### Audit Pass — Polish & Bug Fixes ✅

| Task | Status | Notes |
|------|--------|-------|
| Add numpy, pillow, opencv-python to pyproject.toml | ✅ | Required deps |
| Add torch, open-clip-torch as optional `[clip]` extra | ✅ | `uv add torch open-clip-torch` |
| Fix thread-unsafe private var access in summarization_pipeline | ✅ | Uses public `get_all_thread_ids()` |
| Fix recall_events drill-down (was stopping after 1 level) | ✅ | Now walks all levels |
| Remove unused `_LEVELS_FINE_FIRST` from memory_tools | ✅ | |
| Remove stale `pyexpat.errors` import from webapp.py | ✅ | |
| Remove redundant `get_event_log()` call in pipeline._tick | ✅ | |

---

## ⏩ NEXT SESSION — Start Here

### Install deps first (not yet done)
```bash
uv add numpy pillow opencv-python
# optional — for CLIP semantic frame search:
uv add torch open-clip-torch
```

### Then verify imports
```bash
.venv/Scripts/python.exe -c "import numpy, PIL, cv2; print('OK')"
```

### Then start the server
```bash
.venv/Scripts/langgraph dev
```

### Then run end-to-end test
1. Open the chat UI in browser
2. Enable camera → WebSocket should connect
3. Move in front of camera → motion should trigger LLaVA caption → EventLog
4. Ask: **"what do you see right now?"** → `describe_camera_view`
5. Ask: **"what happened in the last 5 minutes?"** → `recall_events`
6. Ask: **"what color is my shirt?"** → `visual_detail_query`
7. Wait ~5 min → check a 5-min summary node was created in MemoryStore

---

## Steps Still Planned

### Step 6 — Proactive Loop (deferred — not needed now)
**Goal:** Background watcher that pushes alerts without being asked.
Revisit when integrating with robot hardware.

| Task | Status | File |
|------|--------|------|
| Event watcher thread | ⏳ | `src/utils/proactive_loop.py` |
| Alert rules (person entered, long idle, etc.) | ⏳ | `src/utils/proactive_loop.py` |
| WebSocket push to client | ⏳ | `src/webapp.py` |

---

### Step 7 — Audio Perception (Future)
**Goal:** Whisper-based speech-to-text + sound event detection.

| Task | Status | File |
|------|--------|------|
| Microphone / audio stream capture | ⏳ | `src/utils/audio_capture.py` |
| Whisper transcription | ⏳ | `src/utils/audio_capture.py` |
| Sound event detection (clap, alarm, door) | ⏳ | `src/utils/audio_capture.py` |
| Feed transcripts into EventLog with `audio` tag | ⏳ | `src/utils/event_log.py` |

---

### Step 8 — Expression / Emotion Detection (Future)
**Goal:** Detect facial expressions and body language from frames.

| Task | Status | File |
|------|--------|------|
| DeepFace / MediaPipe integration | ⏳ | `src/utils/expression_detector.py` |
| Emotion tagging on motion events | ⏳ | `src/utils/perception_loop.py` |

---

### Step 9 — Robot Action Tools (Future)
**Goal:** Natural language → structured movement commands for robot hardware.

| Task | Status | File |
|------|--------|------|
| `move_forward(meters)` tool | ⏳ | `src/tools/robot_tools.py` |
| `turn(degrees, direction)` tool | ⏳ | `src/tools/robot_tools.py` |
| `stop()` tool | ⏳ | `src/tools/robot_tools.py` |
| ROS / serial / GPIO interface | ⏳ | `src/tools/robot_tools.py` |
| Register robot tools in supervisor | ⏳ | `src/tools/__init__.py` |

---

## Existing Baseline (Pre-Implementation)

| Component | Status | Notes |
|-----------|--------|-------|
| `frame_buffer.py` | ✅ | Updated with timestamps + time-window eviction |
| `vision_tools.py` | ✅ | `describe_camera_view` — current frame only |
| `supervisor_agent.py` | ✅ | ReAct supervisor with all tools bound |
| `video_analysis_agent.py` | ✅ | Video analysis subagent |
| `webapp.py` | ✅ | FastAPI + WebSocket + lifespan + perception loop wired |
