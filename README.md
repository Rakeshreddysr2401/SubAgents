# SubAgents — Perceptual AI Desktop Assistant

SubAgents is a multimodal AI assistant designed to run locally, providing "eyes" through your webcam and a "voice" through your speakers. It leverages **LangGraph**, **FastAPI**, and **Ollama/llama.cpp** to create a proactive, conversational agent that can see, hear, and interact with its environment.

## 🚀 Key Features

- **Multimodal Perception**: Uses a webcam to see and describe your environment in real-time.
- **Conversational Voice**: Speaks responses out loud using the macOS `say` command.
- **Persistent Memory**: Remembers visual context across conversation turns (powered by LangGraph checkpointers).
- **Tool-Integrated Agent**: A ReAct-style supervisor agent that dynamically decides when to look at the camera, check system info, or speak.
- **Local-First**: Designed to run with local LLMs (like LLaVA or Gemma) via Ollama or llama.cpp for privacy and speed.
- **Interactive UI**: Includes a custom web-based chat interface with real-time video streaming.

## 🏗️ Architecture

The system is built with a modular agentic architecture:

- **Frontend**: A self-contained HTML/JS UI that streams webcam frames via WebSockets and communicates with the backend via Server-Sent Events (SSE).
- **Backend (FastAPI)**: Manages WebSocket connections for video frames, handles chat requests, and orchestrates the LangGraph runtime.
- **Agent (LangGraph)**:
  - **Supervisor Agent**: The brain that processes messages and decides which tools to call.
  - **Tool Layer**: 
    - `capture_webcam`: Retrieves the latest frame from the buffer for visual analysis.
    - `speak_out_loud`: Triggers macOS text-to-speech.
    - `get_system_info`: Reports time, date, and battery status.
- **Frame Buffer**: An in-memory rolling buffer that holds the latest camera frames for the agent to "see."

## 📁 Project Structure

```text
SubAgents/
├── src/
│   ├── agents/          # LangGraph agent definitions (Supervisor)
│   ├── configs/         # Logging and persistence configuration
│   ├── models/          # Data schemas for API requests
│   ├── states/          # LangGraph state definitions
│   ├── tools/           # Tool implementations (Vision, Audio, System)
│   ├── utils/           # Utilities (Frame buffering)
│   ├── llm_config.py    # LLM and provider setup (Ollama/llama.cpp)
│   └── webapp.py        # FastAPI server and WebSocket handler
├── static/              # Web UI (index.html)
├── graph.py             # Compiled LangGraph entry point
├── langgraph.json       # LangGraph deployment config
├── pyproject.toml       # Dependencies and project metadata
└── wake_word.py         # Script for voice-activation/triggering
```

## 🛠️ Setup & Installation

### 1. Prerequisites
- **Python 3.11+**
- **uv** (recommended for dependency management)
- **macOS** (required for `say` command and system tools)
- **Local LLM Server**: [Ollama](https://ollama.ai) or [llama.cpp](https://github.com/ggerganov/llama.cpp) running a multimodal model (e.g., LLaVA).

### 2. Install Dependencies
```bash
uv sync
```

### 3. Configuration
Create a `.env` file in the root directory:
```env
LLAMA_CPP_BASE_URL=http://localhost:8080/v1  # Or Ollama URL
SUPERVISOR_MODEL=multimodal-model            # Name of your model
```

### 4. Start the Application
Run the LangGraph development server:
```bash
langgraph dev
```
Access the UI at `http://127.0.0.1:2024`.

## 🤖 Usage Examples

- **Visual Queries**: "What am I holding right now?" or "Describe what you see."
- **System Info**: "How is my battery looking?"
- **Voice Control**: "Speak your response out loud."
- **Contextual Memory**: "Who was that in the frame 2 minutes ago?" (Requires persistent memory enabled).

## 🛡️ Security Note
The application uses Bearer tokens for API access. Ensure you enter your token in the settings bar of the UI to authorize chat requests.
