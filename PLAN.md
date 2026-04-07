# Perceptual Memory System — Architecture Plan

## Vision

Build a human-like perceptual assistant that:
- Continuously watches via camera (event-driven, not every frame)
- Remembers what happened across multiple time horizons
- Can answer both broad ("what happened this morning?") and
  fine-grained ("how many buttons on his shirt?") queries
- Acts proactively, not just reactively

---

## Architecture Overview

```
Camera Feed
    │
    ├──[Motion Gate]── no motion ──► discard
    │   (OpenCV absdiff, ~1ms)
    │
    │   motion detected
    ▼
[Frame Store]                    [Event Log]
 Compressed JPEG + timestamp      Raw VLM captions + timestamp
 CLIP embedding per frame         Rolling, keyed by thread_id
 Rolling 5-min window
    │
    │ every 5 min
    ▼
[Summarization Pipeline]  ◄── background scheduler
    │
    ├── 5-min  summaries  (2x per 10-min)
    ├── 10-min summaries  (3x per 30-min)
    ├── 30-min summaries  (2x per 1-hr)
    ├── 1-hr   summaries  (12x per 12-hr)
    ├── 12-hr  summaries  (2x per daily)
    └── daily  summaries  (7x per weekly)
    │
    ▼
[Memory Store]  — tree of MemoryNodes, each knows its children
    │
    ▼
[Query Router]  — decides which level + whether to drill down
    │
    ├── broad query   ──► search summaries, return best match
    │
    └── detail query  ──► search summaries → drill down → raw frames
                          (CLIP semantic search as last resort)
```

---

## Memory Hierarchy

| Level   | Covers   | Children            | Stored for  |
|---------|----------|---------------------|-------------|
| raw     | ~seconds | —                   | 5 min       |
| 5min    | 5 min    | raw events          | 3 hrs       |
| 10min   | 10 min   | 2x 5min             | 6 hrs       |
| 30min   | 30 min   | 3x 10min            | 12 hrs      |
| 1hr     | 1 hr     | 2x 30min            | 48 hrs      |
| 12hr    | 12 hrs   | 12x 1hr             | 2 weeks     |
| daily   | 24 hrs   | 2x 12hr             | indefinite  |

### Drill-Down Query Flow

```
User: "what happened around 2pm?"
  → search 12hr summaries → find "afternoon block"
  → drill into 12x 1hr summaries → find "2pm-3pm"
  → drill into 2x 30min summaries → find relevant block
  → drill into 3x 10min summaries → find relevant block
  → drill into 2x 5min summaries → return detail
  → if still need pixel detail → CLIP search raw frames
```

---

## Components

### Implemented
- `src/utils/frame_buffer.py` — rolling frame buffer (basic, no timestamps yet)
- `src/tools/vision_tools.py` — `describe_camera_view` tool (current frame only)
- `src/agents/supervisor_agent.py` — ReAct supervisor
- `src/agents/video_analysis_agent.py` — video analysis subagent

### In Progress
- `src/utils/frame_buffer.py` — add timestamps + time-window eviction
- `src/utils/memory_store.py` — MemoryNode tree (Step 1)
- `src/utils/event_log.py` — raw timestamped event captions (Step 2)

### Planned
- `src/utils/summarization_pipeline.py` — rolling background summarizer (Step 3)
- `src/tools/memory_tools.py` — `recall_events` + `visual_detail_query` tools (Step 4)
- `src/utils/frame_store.py` — compressed frames + CLIP embeddings (Step 5)
- `src/utils/perception_loop.py` — motion gate + async VLM captioning (Step 5)
- Proactive background reasoning loop (Step 6)
- Audio perception via Whisper (Step 7)
- Facial expression / emotion detection (Step 8)

---

## Technology Stack

| Concern              | Tool                        |
|----------------------|-----------------------------|
| Motion gate          | OpenCV `absdiff`            |
| Object detection     | YOLOv8n (ultralytics)       |
| Local VLM            | LLaVA via Ollama            |
| Semantic frame search| CLIP (open_clip ViT-B/32)   |
| Summarization LLM    | GPT-4o-mini (existing)      |
| Memory store         | In-memory Python (thread-safe) |
| Audio (future)       | OpenAI Whisper              |
| Expression (future)  | DeepFace / MediaPipe        |

---

## Query Routing Logic

```
User query
  │
  ├── contains "just now" / "right now"     → raw event log (last 60s)
  ├── contains time ref ("2pm", "morning")  → drill down from 12hr
  ├── contains "today" / "this morning"     → hourly summaries
  ├── contains detail words                 → CLIP + raw frames
  │   ("how many", "color", "wearing",
  │    "button", "watch", "read", "count")
  └── general ("what happened")             → most recent 30min summary
```

---

## Key Design Decisions

1. **Event-driven not polling** — VLM only runs on motion, not every frame
2. **Two tracks** — text summaries (fast, lossy) + raw frames (slow, lossless)
3. **Drill-down not scan** — queries traverse the tree top-down, stop when sufficient
4. **Async captioning** — VLM runs in background thread, never blocks the chat
5. **CLIP as last resort** — semantic frame retrieval only when text fails
