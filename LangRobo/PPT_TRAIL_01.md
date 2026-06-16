# LangRobo — Complete PPT Content
# India Agentic AI Open Hackathon 2026
# Copy-paste into the Google Slides template, slide by slide.
# Total: 13 slides (within 15 limit)

---

## SLIDE 1 — COVER SLIDE
(Keep NVIDIA + Open Hackathons branding. Just fill in:)

Title:    India Agentic AI Open Hackathon
Team:     [YOUR TEAM NAME]
Track:    Multi-Agent Workflows

---

## SLIDE 2 — CONTENTS
(Keep as-is from template. Just confirm the 4 sections are listed.)

Contents:
1. Team Introduction
2. AI Use Case
3. Tech Stack
4. Road Map

---

## SLIDE 3 — SECTION HEADER: TEAM INTRODUCTION
(Keep the NVIDIA header slide as-is. Just fill in:)

TEAM INTRODUCTION
Skillset / Experience

---

## SLIDE 4 — TEAM SKILLSET & EXPERIENCE
(This is the content slide under Team Introduction)

**Team**

| Name | Role | Organisation |
|------|------|-------------|
| Rakesh | Software Engineer | Independent |

---

**Skillset — Agentic AI Tools & Frameworks**

- LangGraph (multi-agent orchestration, supervisor routing, tool-bound agents, stateful graphs)
- LangChain (tool definitions, MCP adapters, multi-LLM provider abstraction)
- ROS2 Jazzy (distributed pub/sub, service calls, multi-device messaging across Jetson + Pi5 + ESP32)
- micro-ROS (embedded ROS2 bridge to ESP32 over WiFi UDP for real-time motor control)

---

**Current AI Deployment Setup**

- Inference: llama.cpp serving any GGUF model locally on Mac Mini (OpenAI-compatible HTTP endpoint)
- Supports: OpenAI API, Anthropic API, Google Gemini, Ollama — switchable via one config line
- Planned: NVIDIA NIM as drop-in replacement (same OpenAI-compatible interface, zero code change)

---

**NVIDIA Tools & Libraries — Currently Used**

- Jetson Orin Nano 8GB with CUDA acceleration for all neural inference workloads
- Isaac ROS: SLAM, Nav2 navigation stack, nvblox 3D mapping, image pipelines
- RealSense RGBD camera integration via Isaac ROS image pipelines
- NITRO with Isaac ROS for optimised robotics pipeline deployment
- Official Jetson containers for: Moondream VLM, YOLO object detection, Whisper STT, Kokoro TTS

**NVIDIA Tools — Planned**

- NVIDIA NIM: Nemotron model as LLM backend (one config line switch)
- TensorRT: optimise local VLM inference latency on Jetson GPU
- Isaac Sim: simulation environment for agent behaviour testing without physical hardware

---

**Past AI Hackathon Experience**

- First hackathon participation. (Honest — reviewers respect this.)

---

## SLIDE 5 — SECTION HEADER: AI USE CASE
(Keep NVIDIA header slide as-is. Just fill in:)

AI Use Case
Expand on your project

---

## SLIDE 6 — AI USE CASE: PROJECT DETAILS
(Top-right box: TRACK | A)

**Project Title**
LangRobo — A Local-First Multi-Agent Embodied AI Personal Assistant

---

**Project Description**

LangRobo is a physical AI companion that sees, listens, thinks, speaks, and moves —
using a multi-agent AI brain running entirely on local hardware.

A supervisor agent understands user intent and routes every request to the right
specialist: conversation, vision, navigation, status, food ordering, or delivery tracking.
Each specialist has physical tools — moving the robot, describing what it sees,
navigating to rooms — that create real-world consequences from natural language commands.

Core intelligence (speech recognition, visual reasoning, LLM reasoning, SLAM navigation)
runs entirely on local hardware. Internet is used only for genuinely external services
(food ordering, web search). If connectivity drops, the robot still hears, sees,
thinks, speaks, and navigates.

---

**Project Motivation**

Built from personal frustration: every "smart" assistant either needs constant cloud
connectivity for basic tasks, or sends private data to external servers. A robot that
lives in your home — hearing your conversations, mapping your rooms, learning your
routines — should not depend on infrastructure you don't control.

This project is actively running on physical hardware (Jetson Orin 8GB, Raspberry Pi 5,
ESP32 chassis) in a home environment. Navigation, vision, and voice pipelines are
calibrated and working end-to-end.

The long-term goal is a personal assistant that genuinely learns and grows with the
user over time — not a generic product, but something that becomes yours.

---

**Dataset for Training and Inferencing**

| Model | Dataset | License | Scale |
|-------|---------|---------|-------|
| Whisper small (STT) | Pre-trained by OpenAI | MIT | 680,000 hrs multilingual audio |
| Moondream VLM (vision) | Pre-trained | Apache 2.0 | 1.2B parameters |
| YOLO (object detection) | Pre-trained COCO | AGPL-3.0 | 118k images, 80 classes |
| Kokoro TTS | Pre-trained | Apache 2.0 | — |
| Local GGUF LLM | Pre-trained (Llama/Mistral/Phi family) | Model-specific | 7B–13B parameter range |

**Planned dataset for personalization fine-tuning:**
- Source: locally collected interaction logs (user commands, agent responses, corrections)
- Scale: estimated 500–2,000 interaction turns per month per household
- License: user-owned, never uploaded, processed on-device only
- Purpose: weekly local fine-tuning of the LLM for user-specific vocabulary,
  room names, preferences, and interaction style

---

**Results Achieved**

- End-to-end voice → physical action latency: ~2–3 seconds on local hardware
- Navigation calibrated to 0.28 m/s linear speed, 1.2 rad/s rotation
- Multi-agent routing working: supervisor correctly routes across all specialist agents
- Autonomous delivery workflow: food ordered → delivery tracked → robot navigates to door
  without any second instruction
- LangGraph Studio integration: full agent graph visible and debuggable in real time
- StubBridge mode: entire AI brain testable on any laptop without physical robot

---

## SLIDE 7 — AI USE CASE: REAL-WORLD PROBLEMS WE SOLVE
(Additional content slide — use one of your "more than one slide per section" allowance)

**The Bottleneck We Address**

The gap between AI software and physical hardware is the real bottleneck in
embodied AI. A developer can build a brilliant LLM agent in an afternoon.
Making it hear a person, see the room, navigate across a house, and respond
physically — requires mastering robotics middleware, embedded firmware,
neural inference pipelines, and multi-device coordination simultaneously.

LangRobo demonstrates that this full stack can be built with commodity chips
at accessible cost. The same multi-agent pattern applies across:

| Real-World Domain | Bottleneck Solved |
|------------------|-------------------|
| Home assistance | Personal assistant without cloud dependency or privacy risk |
| Elderly care | Medication reminders, fall detection, emergency navigation, companionship |
| Hospital corridors | Patient guidance, room navigation, multilingual support |
| Restaurant service | Order taking, table navigation, multilingual customer interaction |
| Retail stores | Customer assistance, inventory guidance, store navigation |
| Public transport | Ticket verification, accessibility support, multilingual announcements |
| Schools | Interactive tutoring assistant that navigates and responds physically |

**India-Specific Opportunity**

India requires AI systems that work in low-connectivity environments and support
regional languages. LangRobo is designed for multilingual pipelines:
Telugu, Hindi, Tamil, Kannada, Malayalam, Bengali. Local inference means it works
in rural areas, hospitals, and schools regardless of internet quality.

---

## SLIDE 8 — SECTION HEADER: TECH STACK
(Keep NVIDIA header slide as-is. Just fill in:)

Tech Stack
Strategy for building and deploying LangRobo

---

## SLIDE 9 — TECH STACK: DETAILS
(This is the content slide under Tech Stack)

**AI Frameworks — Currently Used**

| Framework | Role |
|-----------|------|
| LangGraph 0.3.34 | Multi-agent supervisor graph, stateful routing, tool-bound agents |
| LangChain MCP | Swiggy food ordering integration via Model Context Protocol |
| ROS2 Jazzy | Distributed messaging across Jetson, Pi5, ESP32 |
| micro-ROS | Real-time embedded bridge Pi5 ↔ ESP32 over WiFi UDP |

---

**NVIDIA SDKs and Tools**

| NVIDIA Tool | How Used |
|-------------|----------|
| Jetson Orin Nano 8GB + CUDA | GPU acceleration for all neural inference |
| Isaac ROS | SLAM, Nav2, nvblox 3D mapping, RealSense RGBD image pipelines |
| NITRO + Isaac ROS | Optimised robotics pipeline deployment on Jetson |
| Jetson Containers | Containerised Moondream VLM, YOLO, Whisper, Kokoro TTS with CUDA |
| NVIDIA NIM (planned) | Nemotron as LLM backend — OpenAI-compatible, one config line switch |
| TensorRT (planned) | Optimise VLM inference latency on Jetson |

---

**Model Training / Fine-Tuning**

Currently: Inference Only (all pre-trained models)

Planned: Local fine-tuning on collected user interaction data
- Tool: NeMo or LoRA-based fine-tuning on the local LLM
- Goal: personalise vocabulary, room names, preferences, and response style
- Data stays on-device — never uploaded

---

**What We Did Differently**

1. Strict layer separation: LangGraph graph has zero ROS2 imports.
   The AI brain runs on any laptop without a robot (StubBridge mode).
   This made development and testing dramatically faster.

2. Multi-device over ROS2 only: Jetson, Pi5, and ESP32 communicate
   exclusively through ROS2 topics. No direct socket calls between devices.
   Adding a new device = adding a new ROS2 publisher or subscriber.

3. Agent-tool separation: each agent has a fixed tool set.
   The supervisor never executes actions — only routes.
   This prevents agents from overstepping their domain.

4. Local-first by design: cloud LLMs are supported but never assumed.
   The system defaults to llama.cpp on the local network.

---

**Potential Bottlenecks**

| Bottleneck | Current State | Mitigation |
|------------|--------------|------------|
| LLM inference latency | ~2–3s per turn on local hardware | TensorRT optimisation; NIM for faster local inference |
| SLAM map requires manual setup | Named locations set manually after mapping | Planned: auto-labeling by asking "what room is this?" |
| VLM (Moondream) accuracy | Good for simple queries, weaker on complex scenes | Upgrade to larger VLM when Jetson memory allows |
| Single point of failure (Mac Mini) | LLM server on Mac Mini; Pi5 can't reason without it | Add fallback: smaller GGUF directly on Jetson |
| No RealSense in current demo | Depth-based object pose estimation unavailable | Fallback 360° VLM scan covers basic object navigation |

---

## SLIDE 10 — SECTION HEADER: ROAD MAP
(Keep NVIDIA header slide as-is. Just fill in:)

Road Map
Ideas for further improvement of the solution.

---

## SLIDE 11 — ROAD MAP: DETAILS

**Areas Where We Want Mentor Support**

- TensorRT optimisation: reducing VLM and LLM inference latency on Jetson
- NVIDIA NIM deployment: best practice for self-hosted Nemotron on edge hardware
- NeMo fine-tuning: pipeline for local on-device personalization fine-tuning
- Isaac Sim integration: simulating multi-room environments for agent testing
  without needing physical hardware for every experiment

---

**Long-Term Goals**

| Timeline | Goal |
|----------|------|
| Month 1–2 | Memory agent: learns names, preferences, room vocabulary from interaction history |
| Month 2–3 | Home automation agent: voice-controlled lights, AC, locks via MQTT / Home Assistant |
| Month 3–4 | Multilingual support: Telugu, Hindi, Tamil pipelines via multilingual Whisper |
| Month 4–6 | Security agent: face recognition, visitor alerts, anomaly detection |
| Month 6–12 | Healthcare agent: medication reminders, fall detection, emergency navigation |
| Year 2 | Multi-robot coordination: same agent brain controlling multiple physical units |

**Ultimate vision:** an embodied AI personal assistant that handles a meaningful
fraction of daily life — locally, privately, in any Indian language, on hardware
anyone can afford.

---

**Key Limitations (Honest Assessment)**

1. SLAM map setup is manual — room coordinates must be entered after each new environment
2. No arm or manipulation capability yet — robot navigates but cannot pick objects
3. LLM inference speed limits real-time conversational feel on edge hardware
4. Moondream VLM struggles with complex multi-object scene understanding
5. Single Mac Mini creates an LLM dependency — if it's off, reasoning stops
6. No persistent long-term memory yet — robot forgets between power cycles

---

**How We Plan to Overcome Them**

| Limitation | Plan |
|------------|------|
| Manual SLAM setup | Auto-labeling: robot asks "what room is this?" after mapping, stores locally |
| No manipulation | New BASE module: robotic arm as ROS2-connected add-on, no other code changes |
| LLM latency | TensorRT optimisation + Nemotron via NIM for faster local inference |
| VLM accuracy | Upgrade to larger VLM (Phi-3 Vision or LLaVA) when Jetson allows |
| LLM single point of failure | Fallback: smaller GGUF directly on Jetson for basic reasoning |
| No persistent memory | Memory agent with local vector store (planned next milestone) |

---

## SLIDE 12 — OPTIONAL: SYSTEM ARCHITECTURE DIAGRAM
(Add this if you have space — judges love a clear diagram)

Copy this text into a diagram tool (Excalidraw, Canva, Lucidchart) or draw it in Slides:

```
  USER VOICE
      │
      ▼
  [Jetson Orin 8GB — HEAD]
  Whisper STT → Isaac ROS → Moondream VLM
  Nav2 + SLAM + nvblox
  Kokoro TTS → Speaker
      │  ROS2 topics  ▲
      ▼               │
  [Raspberry Pi 5 — BODY]
  LangGraph Supervisor
      ├── Conversation Agent
      ├── Vision Agent
      ├── Navigation Agent
      ├── Status Agent
      ├── Food Ordering Agent  ──► [Internet: Swiggy]
      └── Delivery Tracking Agent
      │  micro-ROS / WiFi UDP
      ▼
  [ESP32 — BASE]
  Motor Control → 4WD Chassis

  [Mac Mini — LLM Server]
  llama.cpp / any GGUF ◄──── [Pi5 via HTTP on local network]
  (NVIDIA NIM planned)
```

Caption: All solid lines = local network only. One dashed line = internet (Swiggy only).

---

## SLIDE 13 — CLOSING / DEMO SLIDE
(Optional — judges appreciate seeing a demo plan)

**Demo: One Command, Four Devices, Zero Cloud**

Step 1:  "Go to the kitchen."
         → Jetson: Whisper hears it
         → Pi5: LangGraph routes to Navigation agent
         → Jetson: Nav2 plans path using SLAM map
         → ESP32: motors drive the robot to the kitchen

Step 2:  "What do you see on the table?"
         → Pi5: routes to Vision agent
         → Jetson: Moondream VLM analyses camera frame
         → Jetson: Kokoro speaks the answer

Everything above: NO internet.

Step 3:  "Order biryani."
         → Food agent places order (internet: Swiggy only)
         → Delivery agent monitors in background
         → Robot navigates to door when food arrives (no second command)

LangGraph Studio running on laptop shows every routing decision live.

---

# FILL-IN CHECKLIST BEFORE SUBMITTING

[ ] Slide 1: Replace TEAM NAME with your actual team name
[ ] Slide 3-4: Add your team member photos if you want (optional but memorable)
[ ] Slide 6: Add GitHub link if repo is public
[ ] Slide 12: Draw the architecture diagram properly (don't leave it as ASCII text)
[ ] Slide 13: Replace with screenshot or link to your demo video
[ ] Remove this PPT_CONTENT.md note from slides before submitting
[ ] Submit BEFORE June 19 deadline
