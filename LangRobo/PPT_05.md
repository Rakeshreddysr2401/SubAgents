# LangRobo — PPT Content
# India Agentic AI Open Hackathon 2026 | Track: Multi-Agent Workflows
# 15 slides. Copy slide by slide into the Google Slides template.

---

## SLIDE 1 — COVER

**Title:** India Agentic AI Open Hackathon
**Team:** [YOUR TEAM NAME]
**Track:** Multi-Agent Workflows

**Tagline:**
see → reason → decide → act

---

## SLIDE 2 — CONTENTS

1. Team Introduction
2. AI Use Case
3. Tech Stack
4. Road Map

---

## SLIDE 3 — SECTION HEADER: TEAM INTRODUCTION

**TEAM INTRODUCTION**
Skillset / Experience

---

## SLIDE 4 — TEAM SKILLSET & EXPERIENCE

**Team**

| Name | Role | Organisation |
|------|------|-------------|
| Rakesh | Software Engineer | Independent / Personal Project |

---

**Agentic AI Skills**

| Area | Experience |
|------|-----------|
| Multi-agent orchestration | LangGraph — supervisor routing, stateful graphs, tool-bound agents |
| Agent integrations | LangChain MCP adapters, multi-LLM provider abstraction |
| Robotics middleware | ROS2 Jazzy — distributed pub/sub across Jetson, Pi5, ESP32 |
| Embedded AI | micro-ROS — real-time bridge to ESP32 over WiFi UDP |
| Edge AI inference | llama.cpp, Moondream VLM, Whisper STT, Kokoro TTS on Jetson CUDA |

---

**Current AI Deployment Setup**

- Local inference: llama.cpp on Mac Mini — serves any GGUF model, OpenAI-compatible HTTP
- Multi-provider: OpenAI, Anthropic, Gemini, Ollama — switchable via one config line
- **Hackathon target: NVIDIA NIM as LLM backend — same interface, zero code change**

---

**NVIDIA Tools — Currently Used**

- Jetson Orin Nano 8GB (JetPack 7.2, CUDA) — all neural inference on GPU
- Isaac ROS: cuVSLAM, nvblox 3D mapping, Nav2, image pipelines — installed
- NITROS zero-copy: YOLOv8 → visual_slam → nvblox share GPU memory
- Custom Jetson Containers: Moondream VLM (MLC INT4), YOLOv8s, Whisper, Kokoro TTS

**NVIDIA Tools — Planned for Hackathon**
- NVIDIA NIM: Nemotron as reasoning LLM (live swap target for July 24–25)
- TensorRT: quantise VLM for lower Jetson latency
- Isaac Sim: simulation for agent + navigation testing

**Past hackathon experience:** First participation.

---

## SLIDE 5 — SECTION HEADER: AI USE CASE

**AI Use Case**
Expand on your project

---

## SLIDE 6 — THE PROBLEM & WHAT WE BUILT

**Track: A — Multi-Agent Workflows**

---

**The Problem: Intelligence Lives in the Cloud, Not in the Device**

| Existing Technology | Core Limitation |
|--------------------|-----------------|
| Smart speakers (Alexa, Google Home) | Cannot function without internet — basic tasks require cloud |
| Voice assistants | Your voice, home layout, and routines uploaded to external servers |
| Cloud robots | Latency, privacy risk, subscription costs, internet dependency |
| LLM chatbots (ChatGPT, Gemini) | Screen-only — cannot see the room, move, or act physically |
| Robot vacuums | No semantic understanding — cannot reason about language or context |

**The gap no product fills:**
An AI that is simultaneously intelligent, physical, private, offline-capable, and affordable.

---

**What We Built: LangRobo**

A physical AI companion with a multi-agent brain — running 100% on local hardware.

```
You speak → Supervisor understands → Right specialist acts → Physical world changes
```

- **Sees** the environment (Moondream VLM on Jetson GPU)
- **Hears** you (Whisper STT, wake word — no cloud)
- **Thinks** (LangGraph multi-agent reasoning — local LLM)
- **Speaks** back (Kokoro TTS — no cloud)
- **Navigates** autonomously (Isaac ROS + Nav2 + SLAM)
- **Acts** on external services when needed (Swiggy food ordering via MCP)
- **Learns** your preferences over time (local, never uploaded)

**Internet used for ONE thing only: external services like food ordering.**
Pull the WiFi cable — the robot still hears, sees, thinks, speaks, and moves.

---

## SLIDE 7 — WHY WE WIN: COMPETITIVE DIFFERENTIATION

**What Every Other Team Will Present**

Most hackathon entries in the Multi-Agent Workflows track will be:
- Enterprise chat agents (document Q&A, workflow automation)
- API integration pipelines (multi-step tool calling)
- RAG systems over business data
- Cloud-hosted agent demos with no physical consequence

**These are software agents. They live behind a screen.**

---

**What LangRobo Does That No Other Team Will**

| Dimension | Other Teams | LangRobo |
|-----------|-------------|----------|
| Physical embodiment | Screen only | Real robot that moves in the real world |
| Cloud dependency | Cloud LLM required | Full intelligence runs locally on ₹47k hardware |
| Privacy | Data leaves to cloud | Zero data leaves home network |
| Agentic behavior | Single-turn tool calls | Background task continuation — no second command needed |
| NVIDIA hardware depth | API calls to cloud | Jetson GPU + Isaac ROS + NITROS zero-copy + two-container design |
| Scalability of use cases | One domain | Same agent pattern → home, hospital, restaurant, school, retail |
| Offline capability | Breaks without internet | Core functions work with no connectivity |

**The judges are from NVIDIA.** They will recognize a team that actually ran Isaac ROS,
built a two-container Jetson deployment, and implemented NITROS zero-copy pipelines —
not just called a cloud API.

---

## SLIDE 8 — AGENTIC BEHAVIOR: THE KEY DIFFERENTIATOR

**From Command-Response to Persistent Goal-Oriented Behavior**

Most assistants: you command → they respond → done. One turn. No memory. No initiative.

LangRobo: supervisor routes to specialists that chain autonomously toward a goal.

---

**Example: The Delivery Workflow — One Command, Five Steps, Zero Follow-up**

```
User: "Order biryani."
         │
         ▼
  Supervisor → Food Agent
  Food Agent: search restaurants → browse menu → confirm → place order
         │  chains immediately, no second instruction
         ▼
  Delivery Agent takes over
  Polls delivery status every 2 minutes in background
         │  order arrives — user gave no further command
         ▼
  Robot: "Your order has arrived!"
  Navigation Agent: autonomously drives to front door
  Hands back to Conversation Agent
```

**One instruction. Five-step autonomous workflow. Zero cloud for the decision logic.**

This is the difference between a command executor and an **agent** — one that maintains
goals, monitors state, and initiates action when conditions are met.

---

**Current Working Capabilities (Measured on Physical Hardware)**

| Capability | Status | Evidence |
|-----------|--------|---------|
| Voice → physical action | ✅ Working | ~2–3s end-to-end latency measured |
| Multi-agent routing | ✅ Working | Supervisor routes correctly across all agents |
| Motor navigation | ✅ Working | 0.28 m/s linear, 1.2 rad/s rotation (110 cm measured run) |
| Visual reasoning | ✅ Working | Moondream VLM on Jetson GPU — tested with USB camera |
| Autonomous delivery workflow | ✅ Working | End-to-end: order → track → navigate to door |
| LangGraph Studio live debug | ✅ Working | Full agent graph visible in browser in real time |
| Isaac ROS (SLAM + Nav2) | 🔄 Installed | RealSense D555 in transit — live test on camera arrival |

---

## SLIDE 9 — WHAT IS POSSIBLE: REAL-WORLD SCALE

**One Architecture. Unlimited Domains.**

Adding any new capability = writing one new specialist agent.
The supervisor, routing logic, hardware, and all other agents unchanged.

| Domain | Specialist Agents Needed | Real-World Impact |
|--------|--------------------------|-------------------|
| **Home Assistant** | Memory, Automation, Scheduler | Lights, AC, locks, reminders — offline, private |
| **Elderly Care** | Healthcare, Emergency, Companion | Medication reminders, fall detection, "call family" on emergency |
| **Hospital** | Wayfinding, Patient Guide, Staff Assist | Navigate patients to wards, multilingual, no internet needed |
| **Restaurant** | Order Taking, Table Nav, Multilingual | Takes orders in Telugu/Hindi, navigates to table, sends to kitchen |
| **School** | Tutor, Demo, Q&A | Physically demonstrates experiments, answers student questions locally |
| **Retail** | Product Guide, Inventory, Store Nav | "Where is the sugar?" — robot navigates, shows, speaks |
| **Public Transport** | Ticket, Accessibility, Announcements | Helps differently-abled passengers, multilingual, works offline |
| **Security** | Face Recognition, Anomaly, Alert | Recognizes family, alerts on strangers — all local, no cloud |
| **Warehouse / Logistics** | Inventory Scan, Pick-Route, Status | Navigate aisles, scan shelves, report status via voice |

**India-First:** multilingual Whisper (Telugu, Hindi, Tamil, Kannada, Malayalam, Bengali)
means this works in rural hospitals, regional schools, and local businesses
regardless of internet quality or English proficiency.

---

## SLIDE 10 — DATASET & TECHNICAL POSITIONING

**Dataset for Training and Inferencing**

| Model | Source | License | Scale |
|-------|--------|---------|-------|
| Whisper small (STT) | OpenAI pre-trained | MIT | 680,000 hrs multilingual audio |
| Moondream 2 (VLM) | Pre-trained | Apache 2.0 | 1.8B parameters |
| YOLOv8s (object detection) | COCO pre-trained | AGPL-3.0 | 118k images, 80 classes |
| Kokoro TTS | Pre-trained | Apache 2.0 | — |
| GGUF LLM (reasoning) | Llama / Mistral / Phi / Nemotron | Model-specific | 7B–13B range |

**Model Training — Currently: Inference Only**

**Planned — local personalization fine-tuning:**
- Data: locally collected interaction logs — commands, corrections, preferences
- Scale: ~500–2,000 turns/month per household — processed on-device, never uploaded
- Tool: NeMo or LoRA fine-tuning on local LLM
- Goal: robot learns your vocabulary, room names, and daily patterns over time
- Privacy guarantee: training data and fine-tuned weights stay on the device

---

**Technical Positioning**

LangRobo does not claim to solve general robotics or AGI.

The contribution is **system-level integration**:
multi-agent AI orchestration + multimodal local inference +
distributed robotics middleware + physical embodied execution —
combined into one working, affordable, local-first architecture.

Practical deployable AI. Not research speculation.

---

## SLIDE 11 — SECTION HEADER: TECH STACK

**Tech Stack**
Strategy for building and deploying LangRobo

---

## SLIDE 12 — ARCHITECTURE & NVIDIA STACK

**System Architecture**

```
  USER SPEAKS
       │
       ▼
  ┌──────────────────────────────────────────┐
  │  JETSON ORIN NANO 8GB  ·  HEAD           │
  │                                          │
  │  Container 1 — isaac_ros (NVIDIA NGC)    │
  │    cuVSLAM + nvblox 3D map + Nav2        │
  │    YOLOv8s  [NITROS zero-copy GPU]       │
  │    RealSense D555 depth+RGB+IMU [soon]   │
  │                                          │
  │  Container 2 — ai_stack (jetson build)   │
  │    openWakeWord → Whisper STT            │
  │    Moondream VLM  (MLC INT4, 0.8GB)     │
  │    Kokoro TTS → Speaker                  │
  └──────────────┬───────────────────────────┘
                 │  ROS2 Jazzy (local WiFi only)
                 ▼
  ┌──────────────────────────────────────────┐
  │  RASPBERRY PI 5  ·  BODY                 │
  │  LangGraph Supervisor (pure router)      │
  │    ├── Conversation  ├── Vision          │
  │    ├── Navigation    ├── Status          │
  │    ├── Food ──────────────► [Swiggy]    │
  │    └── Delivery Tracker                  │
  └──────────────┬───────────────────────────┘
                 │  micro-ROS · WiFi UDP
                 ▼
  ┌──────────────────────────────────────────┐
  │  ESP32  ·  BASE  ·  PWM → 4WD Chassis   │
  └──────────────────────────────────────────┘
  ┌──────────────────────────────────────────┐
  │  MAC MINI  ·  LLM Server (local WiFi)    │
  │  llama.cpp · any GGUF                    │
  │  → NVIDIA NIM / Nemotron [hackathon]    │
  └──────────────────────────────────────────┘
```

Internet: ONE line only → Swiggy API. Everything else = local WiFi.
GPU memory budget: 4.8 GB used · 3.2 GB free on Jetson 8 GB.

---

**NVIDIA Stack**

| Tool | How Used |
|------|----------|
| Jetson Orin Nano 8GB + CUDA | All neural inference on GPU |
| Isaac ROS (cuVSLAM, nvblox, Nav2) | SLAM, 3D occupancy mapping, autonomous navigation |
| NITROS zero-copy | YOLOv8 + SLAM + nvblox share GPU memory — no CPU serialization |
| Jetson Containers | Custom-built: Moondream VLM, YOLOv8, Whisper, Kokoro with CUDA |
| **NVIDIA NIM (hackathon target)** | **Nemotron as LLM — swap from llama.cpp, same interface** |
| TensorRT (planned) | Quantise VLM for lower Jetson inference latency |
| Isaac Sim (planned) | Multi-room simulation for agent testing |

---

**Key Design Decisions**

1. **Two-container Jetson design** — Container 1 (NVIDIA NGC) for perception with NITROS
   zero-copy. Container 2 (custom) for voice + VLM. Each upgrades independently.

2. **Zero ROS2 in the LangGraph layer** — entire AI brain runs on any laptop without hardware
   (StubBridge mode). All agents testable in isolation, no robot needed.

3. **ROS2-only inter-device protocol** — Jetson, Pi5, ESP32 talk only via ROS2 topics.
   New hardware = new ROS2 topic. No custom protocols ever.

4. **Supervisor never acts** — only routes. Agents own their tools.
   Prevents scope creep, makes each agent independently testable and replaceable.

5. **Local-first by default** — no API key required to run the full system.
   Cloud LLMs are optional fallback, never a requirement.

---

## SLIDE 13 — BOTTLENECKS & COST

**Potential Bottlenecks & Mitigations**

| Bottleneck | Current State | Plan |
|------------|--------------|------|
| RealSense D555 in transit | SLAM + 3D nav not yet live-tested | Isaac ROS fully installed — plug in and run on arrival |
| LLM latency (~2–3s/turn) | Limits conversational feel | TensorRT + Nemotron via NVIDIA NIM (hackathon target) |
| Mac Mini LLM dependency | Pi5 stops if Mac Mini off | Fallback: small GGUF (Phi-3 mini) directly on Jetson |
| Manual SLAM map setup | Room coordinates entered after mapping | Robot asks "what room is this?" post-mapping, stores locally |
| No persistent memory | Robot forgets on power cycle | Memory agent + ChromaDB local vector store — Month 2 |
| Moondream VLM accuracy | Weaker on complex multi-object scenes | Upgrade to Phi-3 Vision / LLaVA when Jetson memory allows |

---

**Cost — Built for Accessibility**

Base config — full multi-agent pipeline running today:

| Component | Role | Cost |
|-----------|------|------|
| Jetson Orin Nano 8GB | HEAD — perception + GPU inference | ~₹35,000 |
| Raspberry Pi 5 | BODY — LangGraph brain | ~₹7,000 |
| ESP32 + 4WD chassis | BASE — motor control | ~₹2,500 |
| Basic camera + sensors | Vision input | ~₹2,000 |
| **Base Total** | | **~₹47,000** |

Optional upgrades (each improves capability, none required):

| Add-on | Benefit | Cost |
|--------|---------|------|
| RealSense D555 | Full 3D SLAM + depth navigation | ₹20,000–₹35,000 |
| Mac Mini (LLM server) | Larger models, faster reasoning | ~₹50,000 |

**Commercial intelligent robots: ₹5,00,000 – ₹50,00,000**
LangRobo achieves comparable intelligence at **1/10th the cost.**

---

## SLIDE 14 — SECTION HEADER: ROAD MAP

**Road Map**
Ideas for further improvement of the solution

---

## SLIDE 15 — ROAD MAP, HACKATHON PLAN & CLOSE

**Mentor Support Requested**

- **Isaac ROS + D555 calibration** — cuVSLAM tuning for indoor home environments
- **NVIDIA NIM on edge** — running Nemotron locally on Jetson or Mac Mini
- **TensorRT optimisation** — quantising Moondream VLM + local LLM for Jetson
- **NeMo fine-tuning pipeline** — on-device weekly personalization, data never leaves home
- **Isaac Sim** — multi-room simulation for agent + navigation testing

---

**Hackathon Plan — What We Build on July 24–25 in Bangalore**

| Day | Target | Deliverable |
|-----|--------|-------------|
| Day 1 AM | Swap llama.cpp → NVIDIA NIM (Nemotron) | Robot reasoning on Nemotron via NIM endpoint |
| Day 1 PM | Benchmark: latency + quality vs llama.cpp | Side-by-side comparison, same commands |
| Day 2 AM | Tune routing prompts for Nemotron behaviour | Optimised supervisor + agent prompts |
| Day 2 PM | **Live demo: full pipeline on Nemotron** | Voice → NIM reasoning → physical action |

The NIM swap is a single config line change. The 2 days are for tuning, benchmarking,
and demonstrating — not debugging a risky integration.

---

**Roadmap — Every Row = One New Agent File**

| Timeline | Capability | Impact |
|----------|-----------|--------|
| Month 1 | Memory agent | Remembers names, preferences, room vocabulary locally |
| Month 1 | LLM fallback on Jetson | No single point of failure — works without Mac Mini |
| Month 2 | Home automation agent | Voice-controlled lights, AC, locks via MQTT |
| Month 3 | Multilingual pipeline | Telugu, Hindi, Tamil, Kannada — works offline |
| Month 4–6 | Security agent | Face recognition, visitor alerts — local processing only |
| Month 6–12 | Healthcare agent | Medication reminders, fall detection, emergency navigation |
| Year 2 | Multi-robot fleet | Same brain, multiple robots, coordinated across a building |

**The architecture does not change. Every new capability is one new agent.**
**The ceiling is open.**

---

**"see → reason → decide → act"**

*The future of AI is not only conversational.*
*It is embodied. Local. Reliable. Private. Affordable.*

[YOUR TEAM NAME] · [GitHub link] · India Agentic AI Open Hackathon 2026

---

# SUBMIT CHECKLIST

[ ] Slide 1: Fill in team name
[ ] Slide 4: Confirm organisation name
[ ] Slide 10: Add GitHub repo link
[ ] Slide 12: Redraw architecture diagram in Canva/Excalidraw — not ASCII
[ ] Slide 15: Add LangGraph Studio screenshot showing live agent routing

HONESTY — say exactly this if asked about SLAM:
"Isaac ROS fully installed. RealSense D555 in transit. Live SLAM test begins on arrival."

HACKATHON DAY PITCH (30 seconds):
"We already have a working robot. In Bangalore we're doing one thing:
swapping the LLM from llama.cpp to NVIDIA Nemotron via NIM and benchmarking the result live.
One config line. Two days of tuning and demo."

DEMO VIDEO — record before June 19:
1. Voice command → robot physically moves (Pi5 + ESP32, no internet)
2. Vision query → robot speaks answer (Moondream on Jetson, no internet)
3. LangGraph Studio graph lighting up — visual proof of multi-agent routing

DEADLINE: June 19, 2026
