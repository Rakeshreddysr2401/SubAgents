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
| Edge AI inference | llama.cpp, Moondream VLM, Whisper STT, Kokoro TTS on Jetson GPU |

---

**Current AI Deployment Setup**

- Local inference: llama.cpp serving any GGUF model on Mac Mini (OpenAI-compatible HTTP)
- Switchable via config: OpenAI API, Anthropic, Google Gemini, Ollama, or any local endpoint
- Planned: NVIDIA NIM as drop-in LLM backend — same interface, zero code change

---

**NVIDIA Tools — Currently Used**

- Jetson Orin Nano 8GB (JetPack 7.2, CUDA) — all neural inference on GPU
- Isaac ROS: cuVSLAM, nvblox 3D mapping, Nav2, image pipelines — fully installed
- NITROS zero-copy: YOLOv8 → visual_slam → nvblox share GPU memory, no CPU round-trip
- Custom Jetson Containers: Moondream VLM (MLC INT4), YOLOv8s, Whisper, Kokoro TTS

**NVIDIA Tools — Planned**

- NVIDIA NIM: Nemotron as reasoning LLM (one config line switch)
- TensorRT: quantise VLM for lower latency on Jetson
- Isaac Sim: multi-room simulation for agent testing without physical hardware

**Past hackathon experience:** First participation.

---

## SLIDE 5 — SECTION HEADER: AI USE CASE

**AI Use Case**
Expand on your project

---

## SLIDE 6 — THE PROBLEM & WHAT WE BUILT

**Track: A — Multi-Agent Workflows**

---

**The Problem**

Every "smart" device today is secretly dumb.

| Existing Technology | Core Limitation |
|--------------------|-----------------|
| Smart speakers | Cannot function without internet |
| Voice assistants | Your voice and data leave your home |
| Robot vacuums | No semantic understanding — cannot reason |
| Cloud robots | Latency, privacy risk, internet dependency |

The intelligence does not live in the device. It lives in someone else's data center.

For a robot that maps your home, hears your conversations, and learns your routines —
this is unacceptable.

---

**What We Built**

**LangRobo** — a physical AI companion that sees, listens, thinks, speaks, and moves
using a multi-agent brain running entirely on local hardware.

- A supervisor agent understands intent and routes to the right specialist
- Specialists have physical tools: moving the robot, describing what it sees, navigating rooms
- Core intelligence runs 100% locally — no cloud needed for basic operation
- Internet used for ONE thing only: external services like food ordering

**Built on:** LangGraph · ROS2 · micro-ROS · Isaac ROS · Jetson CUDA · llama.cpp

**Project Motivation:**
Built from personal frustration — every smart assistant sends your data somewhere else.
A robot that lives in your home should answer only to you.

---

## SLIDE 7 — REAL-WORLD IMPACT & INDIA OPPORTUNITY

**The Same Architecture Applies Everywhere**

LangRobo is a home assistant today. The multi-agent architecture is domain-agnostic.
The same supervisor + specialist pattern works across:

| Domain | Real-World Problem Solved |
|--------|--------------------------|
| **Home** | Private personal assistant — offline-capable, learns your routines |
| **Elderly Care** | Medication reminders, fall detection, emergency navigation, companionship |
| **Hospitals** | Patient guidance, room navigation, multilingual staff support |
| **Restaurants** | Order taking, table navigation, multilingual customer interaction |
| **Schools** | Interactive tutoring assistant that physically navigates and demonstrates |
| **Retail** | Customer assistance, product location, inventory guidance |
| **Public Transport** | Ticket verification, accessibility support, multilingual announcements |

Adding any new domain = writing one new specialist agent. The rest of the system unchanged.

---

**India-First Advantage**

India needs AI that works without reliable internet and speaks regional languages.
LangRobo is designed for exactly this:

- **Offline-capable:** core intelligence (speech, vision, reasoning, navigation) works without internet
- **Multilingual pipeline:** architecture supports Telugu, Hindi, Tamil, Kannada, Malayalam, Bengali
  via multilingual Whisper STT and regional TTS models
- **Affordable:** ₹47,000 base hardware vs ₹5–50 lakh for commercial equivalents
- **Deployable in rural areas, hospitals, and schools** regardless of connectivity quality

---

## SLIDE 8 — AGENTIC BEHAVIOR: THE KEY DIFFERENTIATOR

**From Command-Response to Persistent Goal-Oriented Behavior**

Most assistants are reactive. You command → they respond → done.

LangRobo is different. Once a goal is set, agents continue working autonomously.

---

**Example: The Delivery Workflow**

```
User says: "Order biryani."
        │
        ▼
  Supervisor routes → Food Agent
  Food Agent: search → browse → confirm → place order
        │
        ▼  (chains immediately, no second instruction)
  Delivery Agent takes over
  Monitors delivery status every 2 minutes in background
        │
        ▼  (order arrives — no command from user)
  Robot speaks: "Your order has arrived!"
  Navigation Agent: autonomously drives to front door
  Delivery Agent: hands back to Conversation Agent
```

**The user gave one instruction. The robot completed a 4-step workflow.**

This is true agentic behavior — not scripted, not cloud-dependent, not single-turn.

---

**Current Capabilities (Working on Physical Hardware)**

| Capability | Status | Detail |
|-----------|--------|--------|
| Voice → action | Working | ~2–3s end-to-end latency on local hardware |
| Multi-agent routing | Working | Supervisor routes correctly across all agents |
| Direct motor navigation | Working | 0.28 m/s, 1.2 rad/s (measured over 110 cm run) |
| Visual reasoning | Working | Moondream VLM on Jetson GPU, tested with USB camera |
| Autonomous delivery workflow | Working | Food order → background tracking → door navigation |
| LangGraph Studio debug UI | Working | Full agent graph visible live in browser |
| Isaac ROS (SLAM + Nav2) | Installed | RealSense D555 in transit — live test on arrival |

---

## SLIDE 9 — DATASET & TECHNICAL POSITIONING

**Dataset for Training and Inferencing**

| Model | Source | License | Scale |
|-------|--------|---------|-------|
| Whisper small (STT) | OpenAI pre-trained | MIT | 680,000 hrs multilingual audio |
| Moondream 2 (VLM) | Pre-trained | Apache 2.0 | 1.8B parameters |
| YOLOv8s (object detection) | COCO pre-trained | AGPL-3.0 | 118k images, 80 classes |
| Kokoro TTS | Pre-trained | Apache 2.0 | — |
| GGUF LLM (reasoning) | Llama / Mistral / Phi family | Model-specific | 7B–13B range |

**Model Training:** Currently inference-only on all pre-trained models.

**Planned — local personalization fine-tuning:**
- Data source: locally collected interaction logs (commands, corrections, preferences)
- Scale: ~500–2,000 turns/month per household — never uploaded, processed on-device
- Tool: NeMo or LoRA fine-tuning on the local LLM
- Goal: robot learns your vocabulary, room names, and daily patterns over time

---

**Technical Positioning**

LangRobo does not claim to solve general robotics or AGI.

The contribution is **system-level integration**:
combining multi-agent AI orchestration + multimodal local inference +
distributed robotics middleware + physical embodied execution
into one coherent, working, affordable local-first architecture.

The focus is practical deployable AI — not research speculation.

---

## SLIDE 10 — SECTION HEADER: TECH STACK

**Tech Stack**
Strategy for building and deploying LangRobo

---

## SLIDE 11 — ARCHITECTURE & NVIDIA STACK

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
  │  Container 2 — ai_stack (custom build)   │
  │    openWakeWord → Whisper STT            │
  │    Moondream VLM  (MLC INT4, 0.8GB)     │
  │    Kokoro TTS → Speaker                  │
  └──────────────┬───────────────────────────┘
                 │  ROS2 Jazzy (local WiFi)
                 ▼
  ┌──────────────────────────────────────────┐
  │  RASPBERRY PI 5  ·  BODY                 │
  │  LangGraph Supervisor                    │
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
  │  llama.cpp · any GGUF · → NVIDIA NIM    │
  └──────────────────────────────────────────┘
```

Internet: ONE dashed line only → Swiggy API. Everything else is local WiFi.
GPU memory: 4.8 GB used · 3.2 GB free on Jetson 8 GB.

---

**NVIDIA SDKs & Tools**

| Tool | How Used |
|------|----------|
| Jetson Orin Nano 8GB + CUDA | All neural inference on GPU |
| Isaac ROS (cuVSLAM, nvblox, Nav2) | SLAM, 3D mapping, autonomous navigation |
| NITROS zero-copy | YOLOv8 + SLAM + nvblox share GPU memory — no CPU serialization |
| Jetson Containers | Custom-built: Moondream VLM, YOLOv8, Whisper, Kokoro with CUDA |
| NVIDIA NIM (planned) | Nemotron as LLM — OpenAI-compatible, one config line |
| TensorRT (planned) | Quantise VLM for lower inference latency on Jetson |

---

**Key Design Decisions**

1. **Two-container Jetson design** — Container 1 (NVIDIA NGC isaac_ros) for perception with
   NITROS zero-copy. Container 2 (custom jetson-containers) for voice + VLM.
   Each upgrades independently — no monolithic rebuild.

2. **Zero ROS2 in the LangGraph layer** — the entire AI brain runs on any laptop
   without hardware (StubBridge mode). Agents are testable in isolation.

3. **ROS2-only inter-device communication** — Jetson, Pi5, ESP32 talk only via ROS2 topics.
   Adding any new hardware = adding a ROS2 publisher or subscriber. No custom protocols.

4. **Supervisor never acts** — it only routes. Agents own their tools.
   Prevents scope creep and makes each agent independently testable.

5. **Local-first by default** — llama.cpp on local network. No API key to run.
   Cloud LLMs are supported as optional fallback, never required.

---

## SLIDE 12 — BOTTLENECKS & COST

**Potential Bottlenecks & Mitigations**

| Bottleneck | Current State | Plan |
|------------|--------------|------|
| RealSense D555 in transit | SLAM + 3D nav not yet live-tested | Isaac ROS fully installed — plug in and run on arrival |
| LLM latency (~2–3s/turn) | Limits snappy conversational feel | TensorRT + Nemotron via NVIDIA NIM |
| Mac Mini LLM dependency | Pi5 stops reasoning if Mac Mini off | Fallback: small GGUF (Phi-3 mini) directly on Jetson |
| Manual SLAM map setup | Room coordinates entered after mapping | Robot asks "what room is this?" post-mapping, stores locally |
| Moondream VLM accuracy | Weaker on complex multi-object scenes | Upgrade to Phi-3 Vision / LLaVA when Jetson memory allows |
| No persistent memory | Robot forgets on power cycle | Memory agent + local vector store (ChromaDB) — Month 2 |

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

Expanded config (optional, higher capability):

| Add-on | Benefit | Cost |
|--------|---------|------|
| RealSense D555 depth camera | Full 3D SLAM + depth navigation | ₹20,000–₹35,000 |
| Mac Mini (local LLM server) | Larger GGUF models, faster reasoning | ~₹50,000 |

Commercial robots with comparable intelligence: **₹5,00,000 – ₹50,00,000**

LangRobo achieves this at **1/10th the cost** using commodity chips and local inference.

---

## SLIDE 13 — SECTION HEADER: ROAD MAP

**Road Map**
Ideas for further improvement of the solution

---

## SLIDE 14 — ROAD MAP DETAILS

**Mentor Support Requested**

- **Isaac ROS + D555 tuning:** cuVSLAM parameter calibration for indoor home environments
- **TensorRT optimisation:** quantising Moondream VLM + local LLM for lower Jetson latency
- **NVIDIA NIM on edge:** running Nemotron locally on Jetson or Mac Mini
- **NeMo fine-tuning:** on-device weekly personalization pipeline — data never leaves the home
- **Isaac Sim:** multi-room simulation for agent + navigation testing without physical hardware

---

**Roadmap — Adding Capabilities Without Changing the Core**

| Timeline | Agent / Feature | Real-World Impact |
|----------|----------------|-------------------|
| Month 1 | Memory agent | Remembers names, preferences, room vocabulary |
| Month 2 | Home automation agent | Voice-controlled lights, AC, locks via MQTT |
| Month 3 | Multilingual pipeline | Telugu, Hindi, Tamil, Kannada via Whisper multilingual |
| Month 4–6 | Security agent | Face recognition, visitor alerts, anomaly detection |
| Month 6–12 | Healthcare agent | Medication reminders, fall detection, emergency navigation |
| Year 2 | Multi-robot coordination | Same brain controlling multiple robots across a building |

Every row above = one new agent file + one routing line in supervisor prompt.
**The architecture does not change. The ceiling is open.**

---

**Key Limitations — Honest Assessment**

| Limitation | Fix Plan | Timeline |
|------------|----------|----------|
| SLAM + 3D nav not live-tested yet | Plug in D555, run Isaac ROS on arrival | ~1 week |
| LLM single point of failure (Mac Mini) | Small GGUF fallback directly on Jetson | Month 1 |
| No persistent memory across power cycles | Memory agent + ChromaDB local store | Month 2 |
| Manual SLAM room labeling | Auto-labeling by asking robot on first visit | Month 1 |
| No manipulation capability | Robotic arm as new BASE module via ROS2 | Year 1 |

---

## SLIDE 15 — DEMO & CLOSE

**Demo: One Voice Command. Four Devices. Zero Cloud.**

| Step | Command | What Happens |
|------|---------|-------------|
| 1 | "Go to the kitchen" | Whisper hears → Pi5 routes → ESP32 drives → robot arrives |
| 2 | "What do you see?" | Pi5 routes → Moondream VLM on Jetson → Kokoro speaks answer |
| 3 | "Order biryani" | Food agent orders → Delivery agent watches → robot goes to door on arrival |

Steps 1 and 2: NO internet.
Step 3: internet for Swiggy only. The decision to go to the door happens locally.

LangGraph Studio on laptop shows every agent routing decision live — judges see the brain working.

---

**"see → reason → decide → act"**

*The future of AI is not only conversational.*
*It is embodied.*
*Local. Reliable. Private. Affordable.*

[YOUR TEAM NAME] · [GitHub link] · India Agentic AI Open Hackathon 2026

---

# SUBMIT CHECKLIST

[ ] Slide 1: Fill in team name
[ ] Slide 4: Confirm organisation name
[ ] Slide 9: Add GitHub repo link
[ ] Slide 11: Recreate architecture diagram in Canva / Excalidraw (not ASCII)
[ ] Slide 15: Add LangGraph Studio screenshot showing live agent routing

HONESTY LINE — say exactly this in slides if asked about SLAM:
"Isaac ROS stack fully installed. RealSense D555 in transit. Live SLAM testing begins on arrival."

DEMO VIDEO (record before June 19):
- Voice command → robot moves (Pi5 + ESP32, no internet)
- Vision query → robot speaks (Moondream on Jetson, no internet)
- LangGraph Studio graph lighting up — this is the visual proof of multi-agent routing

DEADLINE: June 19, 2026
