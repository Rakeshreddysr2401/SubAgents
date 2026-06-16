# LangRobo — PPT Content
# India Agentic AI Open Hackathon 2026 | Track: Multi-Agent Workflows
# 15 slides. Copy slide by slide into the Google Slides template.

---

## SLIDE 1 — COVER

Title:   India Agentic AI Open Hackathon
Team:    [YOUR TEAM NAME]
Track:   Multi-Agent Workflows

Tagline: see → reason → decide → act

---

## SLIDE 2 — CONTENTS

1. Team Introduction
2. AI Use Case
3. Tech Stack
4. Road Map

---

## SLIDE 3 — SECTION HEADER: TEAM INTRODUCTION

TEAM INTRODUCTION
Skillset / Experience

---

## SLIDE 4 — TEAM SKILLSET & EXPERIENCE

**Team**

| Name | Role | Organisation |
|------|------|-------------|
| Rakesh | Software Engineer | Independent / Personal Project |

---

**Agentic AI Skills**

| Area | Tools / Experience |
|------|-------------------|
| Multi-agent orchestration | LangGraph — supervisor routing, stateful graphs, tool-bound agents |
| Agent integrations | LangChain MCP adapters, multi-LLM provider abstraction |
| Robotics middleware | ROS2 Jazzy — distributed pub/sub across Jetson, Pi5, ESP32 |
| Embedded systems | micro-ROS — real-time bridge to ESP32 over WiFi UDP |
| Edge AI inference | Moondream VLM, Whisper STT, Kokoro TTS — running on Jetson CUDA |

---

**Current AI Deployment Setup**

- Inference: llama.cpp on local Mac Mini — OpenAI-compatible HTTP endpoint
- Multi-provider support: OpenAI, Anthropic, Gemini, Ollama, or any local endpoint
- Switching provider requires one config line change — no code changes
- Target for hackathon: NVIDIA NIM (Nemotron) as LLM backend

---

**NVIDIA Tools — Currently Used**

- Jetson Orin Nano 8GB, JetPack 7.2, CUDA — neural inference on GPU
- Isaac ROS installed: cuVSLAM, nvblox, Nav2, image pipelines
- NITROS zero-copy pipeline: YOLOv8 → visual_slam → nvblox share GPU memory
- Custom Jetson containers: Moondream VLM (MLC INT4), YOLOv8s, Whisper small, Kokoro TTS
- GPU memory usage confirmed: 4.8 GB across all models, 3.2 GB headroom on 8 GB

**NVIDIA Tools — Planned**

- NVIDIA NIM: Nemotron as reasoning LLM (hackathon target: July 24–25)
- TensorRT: quantise Moondream VLM for lower Jetson latency
- Isaac Sim: multi-room simulation for agent testing

**Past hackathon experience:** First participation.

---

## SLIDE 5 — SECTION HEADER: AI USE CASE

AI Use Case
Expand on your project

---

## SLIDE 6 — PROBLEM STATEMENT & PROJECT OVERVIEW

**Track A — Multi-Agent Workflows**

---

**Problem: Physical AI Assistants Have a Connectivity and Privacy Gap**

Most AI assistants today depend on cloud infrastructure for basic intelligence:

| Technology | Limitation |
|-----------|-----------|
| Smart speakers | Core functions fail without internet connectivity |
| Voice assistants | Voice data, home context, and routines processed on external servers |
| Cloud-connected robots | Latency from round-trips, data privacy concerns, subscription dependency |
| LLM chat assistants | Screen-only — cannot perceive the environment or take physical actions |

For a robot operating inside a home — hearing conversations, mapping rooms,
learning daily routines — sending that data to external servers is a significant
practical concern.

---

**Project: LangRobo**

LangRobo is a physically embodied multi-agent AI system designed to run
core intelligence on local hardware.

A supervisor agent interprets natural language and routes requests to
specialist agents. Each specialist has tools that produce physical consequences:
moving the robot, querying the camera, navigating to a room, or calling
an external service when genuinely required.

**What runs locally (no internet required):**
- Speech recognition — Whisper small on Jetson GPU
- Visual reasoning — Moondream VLM on Jetson GPU
- LLM reasoning — any GGUF model via llama.cpp on local Mac Mini
- Navigation — Isaac ROS SLAM + Nav2 on Jetson
- Text-to-speech — Kokoro TTS on Jetson

**What requires internet (by design):**
- Food ordering via Swiggy (external service)
- Web search in the chat agent (optional, disabled by default)

The Mac Mini is a local server on the home network — not a cloud service.
If it is offline, the robot cannot reason. This is a known limitation we address
in the roadmap via a Jetson fallback model.

**Built using:** LangGraph · ROS2 Jazzy · micro-ROS · Isaac ROS · Jetson CUDA ·
llama.cpp · Moondream · Whisper · Kokoro

**Project Motivation:**
Built to explore whether a physically embodied AI assistant could achieve
useful intelligence using affordable commodity hardware without cloud dependency
for its core perception and reasoning functions.

---

## SLIDE 7 — AGENTIC BEHAVIOR: GOAL-CONTINUATION ACROSS AGENTS

**The Difference Between a Command Executor and an Agent**

A command executor responds to one instruction then stops.
An agent maintains a goal, monitors state, and takes initiative when conditions change.

---

**Demonstrated Workflow: Food Order → Autonomous Door Navigation**

```
User says once: "Order biryani."
        │
        ▼
  Supervisor → routes to Food Agent
  Food Agent: search → browse → confirm → place order via Swiggy MCP
        │
        └─ chains to Delivery Agent immediately, no second instruction
        ▼
  Delivery Agent: polls status every 2 minutes in background
        │
        └─ order arrives — no further user command
        ▼
  Robot speaks: "Your order has arrived."
  Navigation Agent: drives autonomously to front door
  Hands context back to Conversation Agent
```

One user instruction triggers a 5-step workflow that continues in the background
and initiates physical action when a condition is met. The decision logic runs locally.

---

**Measured Results on Physical Hardware**

| Capability | Result |
|-----------|--------|
| Voice → physical action latency | ~2–3 seconds end-to-end on local hardware |
| Motor calibration | 0.28 m/s linear, 1.2 rad/s rotation (measured over 110 cm run) |
| Multi-agent routing | Supervisor routes correctly across all specialist agents |
| Visual reasoning | Moondream VLM tested on Jetson GPU with standard USB camera |
| Food ordering + delivery tracking | Tested: order placed via Swiggy MCP → background polling active → door navigation integrated |
| LangGraph Studio | Full agent graph visible and inspectable live in browser |
| Isaac ROS stack | Fully installed and configured — live SLAM test pending D555 arrival |

---

## SLIDE 8 — USE CASES & EXTENSIBILITY

**The Architecture Is Domain-Agnostic**

The supervisor + specialist agent pattern is not specific to home assistance.
Adding a new domain requires writing one specialist agent. All other components
— supervisor, hardware, routing logic, ROS2 layer — remain unchanged.

Domains where the same architecture applies:

| Domain | What a Specialist Agent Would Do |
|--------|----------------------------------|
| Home assistance | Navigation, reminders, home automation via MQTT |
| Elderly care | Medication reminders, fall detection alerts, emergency workflows |
| Hospital corridors | Patient wayfinding, multilingual guidance, room navigation |
| Restaurant service | Order taking, table navigation, kitchen communication |
| School classrooms | Interactive Q&A, physical demonstration navigation |
| Retail assistance | Product location guidance, inventory queries, store navigation |

The current build demonstrates the pattern with home assistance and food ordering.
Each row above represents a planned specialist agent, not a completed feature.

---

**India-Relevant Design Decisions**

- Core functions operate without internet — suitable for low-connectivity environments
- Whisper multilingual model supports Telugu, Hindi, Tamil, Kannada, Malayalam, Bengali
- Local inference removes per-query cloud costs — relevant for cost-sensitive deployments
- Commodity hardware (Jetson Orin Nano, Pi5, ESP32) available in India

---

## SLIDE 9 — DATASET & TECHNICAL POSITIONING

**Models Used for Inference**

| Model | Source | License | Scale |
|-------|--------|---------|-------|
| Whisper small (STT) | OpenAI pre-trained | MIT | 680,000 hrs multilingual audio |
| Moondream 2 (VLM) | Pre-trained | Apache 2.0 | 1.8B parameters |
| YOLOv8s (detection) | COCO pre-trained | AGPL-3.0 | 118k images, 80 classes |
| Kokoro TTS | Pre-trained | Apache 2.0 | — |
| GGUF LLM (reasoning) | Llama / Mistral / Phi / Nemotron | Model-specific | 7B–13B range |

**Model Training: Currently inference-only on all pre-trained models.**

**Planned — on-device personalization:**
- Collect interaction logs locally (commands, corrections, preferences)
- Estimated scale: ~500–2,000 turns/month per household
- Fine-tune local LLM using NeMo or LoRA — data processed on-device, not uploaded
- Goal: adapt vocabulary, room names, and response style to the specific user over time

---

**Technical Scope**

LangRobo is a system integration project, not a model training or novel algorithm project.

The contribution is combining:
- Multi-agent orchestration (LangGraph)
- Multimodal local inference (Jetson GPU — Whisper, Moondream, Kokoro, YOLOv8)
- Distributed robotics middleware (ROS2, micro-ROS, Isaac ROS)
- Physical embodied execution (Nav2, SLAM, ESP32 motor control)

into one working architecture on commodity hardware, with a clear separation
between what requires internet and what does not.

---

## SLIDE 10 — SECTION HEADER: TECH STACK

Tech Stack
Strategy for building and deploying LangRobo

---

## SLIDE 11 — SYSTEM ARCHITECTURE & NVIDIA TOOLS

**System Architecture**

```
  USER SPEAKS
       │
       ▼
  ┌──────────────────────────────────────┐
  │  JETSON ORIN NANO 8GB  ·  HEAD      │
  │  Hears · Sees · Speaks · Navigates  │
  │  Whisper STT · Moondream VLM        │
  │  Kokoro TTS · Isaac ROS (Nav2)      │
  └──────────────┬───────────────────────┘
                 │  ROS2 (local network)
                 ▼
  ┌──────────────────────────────────────┐
  │  RASPBERRY PI 5  ·  BODY            │
  │  LangGraph Supervisor               │
  │  Conversation · Vision · Navigation │
  │  Status · Food ──► [Swiggy API]     │
  │  Delivery Tracker                   │
  └──────────────┬───────────────────────┘
                 │  micro-ROS
                 ▼
  ┌──────────────────────────────────────┐
  │  ESP32  ·  BASE  ·  4WD motors      │
  └──────────────────────────────────────┘
  ┌──────────────────────────────────────┐
  │  MAC MINI  ·  LLM (local network)   │
  │  llama.cpp / NVIDIA NIM (planned)   │
  └──────────────────────────────────────┘
```

All devices communicate on the local home network.
External internet used only for Swiggy food ordering.

---

**NVIDIA Stack**

| Tool | How Used |
|------|----------|
| Jetson Orin Nano 8GB + CUDA | GPU inference for all neural models |
| Isaac ROS (cuVSLAM, nvblox, Nav2) | SLAM, 3D occupancy mapping, path planning |
| NITROS zero-copy | YOLOv8 + SLAM + nvblox share GPU memory within Container 1 |
| Jetson Containers | Custom build: Moondream, YOLOv8, Whisper, Kokoro with CUDA |
| NVIDIA NIM (planned) | Nemotron as LLM — same OpenAI-compatible interface, config-only swap |
| TensorRT (planned) | Quantise Moondream VLM for lower Jetson inference latency |
| Isaac Sim (planned) | Simulate multi-room environments for agent testing |

---

**Key Design Decisions**

1. **Two-container Jetson design** — Container 1 uses NVIDIA NGC isaac_ros image with
   NITROS zero-copy for perception. Container 2 is a custom jetson-containers build
   for voice and VLM. Each upgrades independently without rebuilding the other.

2. **LangGraph layer has zero ROS2 imports** — the entire agent graph runs on any
   laptop without hardware via StubBridge. All agents are testable in isolation.

3. **ROS2-only inter-device communication** — Jetson, Pi5, and ESP32 communicate
   only through ROS2 topics. Adding new hardware means adding a ROS2 interface,
   not modifying existing code.

4. **Supervisor routes, never acts** — the supervisor agent calls only the handover
   tool. It never executes physical actions. This keeps routing logic separate from
   execution logic and makes each specialist independently testable.

5. **Local-first default** — the system runs without any cloud API keys.
   External LLM providers are supported as optional configuration, not a requirement.

---

## SLIDE 12 — CURRENT STATE, BOTTLENECKS & COST

**Honest Current State**

| Component | Status |
|-----------|--------|
| Multi-agent brain (Pi5 + LangGraph) | Working end-to-end |
| Motor control and calibration (ESP32) | Working — 0.28 m/s, 1.2 rad/s measured |
| Voice pipeline (STT + TTS + wake word) | Tested on Jetson with USB camera |
| Visual reasoning (Moondream VLM) | Working on Jetson GPU with USB camera |
| Food ordering + delivery tracking | Tested: Swiggy MCP order → background polling → door navigation integrated |
| Isaac ROS (SLAM + nvblox + Nav2) | Installed and configured — pending D555 camera |
| RealSense D555 depth camera | Ordered, in transit — live SLAM test on arrival |

---

**Known Bottlenecks**

| Bottleneck | Impact | Mitigation Plan |
|------------|--------|----------------|
| D555 not yet arrived | SLAM + depth navigation untested live | Isaac ROS configured; plug in and test on arrival |
| Mac Mini is required for LLM reasoning | Single point of failure | Add small GGUF fallback directly on Jetson (Month 1) |
| LLM latency ~2–3s per turn | Limits conversational pacing | TensorRT + NVIDIA NIM (hackathon target) |
| SLAM map requires manual room labeling | Setup effort per environment | Auto-labeling planned: robot asks room name on first visit |
| No persistent memory across restarts | Robot does not remember between sessions | Local vector store (ChromaDB) planned Month 2 |

---

**Hardware Cost**

Base configuration — full pipeline running today:

| Component | Role | Approx. Cost |
|-----------|------|-------------|
| Jetson Orin Nano 8GB | Perception + GPU inference | ₹35,000 |
| Raspberry Pi 5 | LangGraph orchestration | ₹7,000 |
| ESP32 + 4WD chassis | Motor control | ₹2,500 |
| USB camera + sensors | Vision input | ₹2,000 |
| **Base total** | | **~₹47,000** |

Optional additions:

| Component | Benefit | Approx. Cost |
|-----------|---------|-------------|
| RealSense D555 | 3D SLAM, depth-based navigation | ₹20,000–₹35,000 |
| Mac Mini (LLM server) | Larger models, faster local reasoning | ₹50,000 |

The base build runs the full multi-agent pipeline on ₹47,000 of commodity hardware.
Adding the RealSense D555 and Mac Mini brings the total to roughly ₹1,20,000.

---

## SLIDE 13 — SECTION HEADER: ROAD MAP

Road Map
Ideas for further improvement of the solution

---

## SLIDE 14 — ROAD MAP & HACKATHON PLAN

**Mentor Support Requested**

- **Isaac ROS + D555 integration** — cuVSLAM parameter tuning for indoor home environments
- **NVIDIA NIM on edge hardware** — deploying Nemotron on Jetson or local Mac Mini
- **TensorRT optimisation** — quantising Moondream VLM for lower Jetson latency
- **NeMo fine-tuning pipeline** — on-device personalization without data leaving the home
- **Isaac Sim** — simulate multi-room environments for agent and navigation testing

---

**What We Plan to Build During the Hackathon (July 24–25, Bangalore)**

The core system is already working. The hackathon days are for one targeted improvement:
swapping the LLM backend from llama.cpp to NVIDIA Nemotron via NIM and validating the result.

| Day | Activity | Deliverable |
|-----|----------|-------------|
| Day 1 AM | Configure NVIDIA NIM endpoint, swap config | Robot reasoning on Nemotron via NIM |
| Day 1 PM | Run same benchmark commands on llama.cpp vs NIM | Latency + quality comparison |
| Day 2 AM | Tune supervisor and agent prompts for Nemotron | Optimised routing prompts |
| Day 2 PM | End-to-end demo: voice → NIM → physical action | Live demonstration |

The LLM swap is a single config line change — the 2 days are spent on
benchmarking, prompt tuning, and demonstrating the result.

---

**Planned Improvements (Post-Hackathon)**

| Timeline | Feature | What It Adds |
|----------|---------|-------------|
| Month 1 | Jetson LLM fallback | Removes Mac Mini as single point of failure |
| Month 1 | SLAM live test + room labeling | D555 arrives → test cuVSLAM, label rooms on first visit |
| Month 2 | Memory agent | Remembers name, preferences, room vocabulary locally |
| Month 2 | Home automation agent | Voice-controlled lights, AC, locks via MQTT |
| Month 3 | Multilingual STT/TTS | Telugu, Hindi, Tamil, Kannada regional pipelines |

Each is a new specialist agent. Supervisor, hardware stack, and ROS2 layer stay unchanged.

---

## SLIDE 15 — DEMO & CLOSE

**Demo: Voice Command → Multi-Agent Routing → Physical Action**

| Step | Voice Input | What Happens | Internet? |
|------|-------------|-------------|-----------|
| 1 | "Go to the kitchen" | Whisper → Pi5 routes → ESP32 drives robot to kitchen | No |
| 2 | "What do you see?" | Pi5 routes → Moondream on Jetson → Kokoro speaks answer | No |
| 3 | "Order biryani" | Food agent orders → Delivery agent watches in background → robot navigates to door on arrival | Swiggy only |

LangGraph Studio on laptop shows every routing decision live during the demo.

---

see → reason → decide → act

[YOUR TEAM NAME] · [GitHub link] · India Agentic AI Open Hackathon 2026

---

# CHECKLIST BEFORE SUBMITTING

FILL IN:
[ ] Slide 1 + 15: Team name
[ ] Slide 9: GitHub repo link (if making repo public)
[ ] Slide 11: Redraw architecture diagram in Canva or Excalidraw — not ASCII text
[ ] Slide 15: Add a screenshot from LangGraph Studio showing live agent routing

ACCURACY:
[ ] Do not claim SLAM is tested end-to-end — it is installed, pending camera
[ ] State Mac Mini dependency clearly — it is a local server, not cloud, but it is required
[ ] Planned features (security, healthcare, etc.) are clearly labelled as planned, not built

DEMO VIDEO — record before June 19:
[ ] Voice command → robot physically moves (no internet)
[ ] Vision query → robot speaks answer (no internet)
[ ] LangGraph Studio graph showing agent routing live

DEADLINE: June 19, 2026
