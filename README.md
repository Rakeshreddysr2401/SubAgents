# SubAgents — Perceptual AI Desktop Assistant

SubAgents is a multimodal AI assistant designed to run locally, providing "eyes" through your webcam and a "voice" through your speakers. It leverages **LangGraph**, **FastAPI**, and **Ollama/llama.cpp** to create a proactive, conversational agent that can see, hear, and interact with its environment.

It also ships a **Swiggy Food Agent** that connects to [Swiggy's MCP platform](https://mcp.swiggy.com/builders/docs/) to let an AI assistant search restaurants, manage a cart, and place food delivery orders.

---

## Key Features

- **Multimodal Perception**: Uses a webcam to see and describe your environment in real-time.
- **Conversational Voice**: Speaks responses out loud using the macOS `say` command.
- **Persistent Memory**: Remembers visual context across conversation turns (powered by LangGraph checkpointers).
- **Tool-Integrated Agent**: A ReAct-style supervisor agent that dynamically decides when to look at the camera, check system info, or speak.
- **Local-First**: Designed to run with local LLMs (LLaVA, Gemma, etc.) via Ollama or llama.cpp for privacy and speed.
- **Interactive UI**: Custom web-based chat interface with real-time video streaming over WebSockets.
- **Swiggy Food Agent**: MCP-powered food ordering agent — search restaurants, browse menus, manage cart, and track delivery.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                        Frontend (UI)                     │
│  HTML/JS SPA  ──SSE──►  Chat stream                      │
│               ──WS──►   Video frames                     │
└────────────────────────────┬─────────────────────────────┘
                             │ HTTP / WebSocket
┌────────────────────────────▼─────────────────────────────┐
│                   Backend (FastAPI)                       │
│  /chat  /history  /events  /ws/frames  /trigger_voice    │
└────────────────────────────┬─────────────────────────────┘
                             │ LangGraph SDK
        ┌────────────────────┴─────────────────────┐
        │              LangGraph Server             │
        │                                           │
        │   Graph: "agent"         Graph: "swiggy_food"  │
        │   (Supervisor Agent)     (Food Ordering Agent) │
        │                                           │
        │   supervisor_node ◄──► ToolNode           │
        │        │                   │              │
        │   capture_webcam     swiggy MCP tools     │
        │   get_system_info    (via HTTP MCP)        │
        │   open_mac_app                            │
        └───────────────────────────────────────────┘
```

### Supervisor Agent (agent graph)

A ReAct-style agent that runs as the default assistant:

```
User input
    └─► supervisor_node (LLM + tools)
              ├─ tool_calls? ──► ToolNode ──► supervisor_node (loop)
              └─ no tools   ──► END
```

**Tools:**
| Tool | Description |
|------|-------------|
| `capture_webcam` | Grabs latest frame from the in-memory buffer, returns as a base64 image |
| `get_system_info` | Returns current time, date, battery status |
| `open_mac_app` | Opens a macOS application by name |

### Swiggy Food Agent (swiggy_food graph)

A food ordering assistant that connects to Swiggy's MCP platform over streamable HTTP:

```
User input
    └─► swiggy_food_node (LLM + 14 Swiggy MCP tools)
              ├─ tool_calls? ──► ToolNode ──► swiggy_food_node (loop)
              └─ no tools   ──► END
```

**Tools (loaded from `mcp.swiggy.com/food`):**

| Category | Tools |
|----------|-------|
| Discover | `search_restaurants`, `search_menu`, `get_restaurant_menu`, `get_addresses` |
| Cart | `get_food_cart`, `update_food_cart`, `flush_food_cart`, `fetch_food_coupons`, `apply_food_coupon` |
| Order | `place_food_order` |
| Track | `get_food_orders`, `get_food_order_details`, `track_food_order` |

---

## Project Structure

```text
SubAgents/
├── src/
│   ├── agents/
│   │   ├── supervisor_agent.py   # Multimodal ReAct supervisor
│   │   └── swiggy_food_agent.py  # Swiggy food ordering agent
│   ├── configs/
│   │   ├── logging_config.py     # Structured logging setup
│   │   └── memory_config.py      # MemorySaver checkpointer
│   ├── models/
│   │   └── schema.py             # API request/response schemas
│   ├── states/
│   │   └── states.py             # AgentState TypedDict
│   ├── tools/
│   │   ├── __init__.py           # Exports ALL_TOOLS
│   │   ├── vision_tools.py       # capture_webcam tool
│   │   ├── audio_tools.py        # speak_out_loud utility
│   │   ├── system_tools.py       # get_system_info, open_mac_app
│   │   └── swiggy_mcp.py         # Swiggy MCP client + SWIGGY_FOOD_TOOLS
│   ├── utils/
│   │   └── frame_buffer.py       # Thread-safe in-memory frame buffer
│   ├── llm_config.py             # LLM setup (Ollama / llama.cpp)
│   └── webapp.py                 # FastAPI server, WebSocket, SSE
├── static/
│   └── index.html                # Web UI
├── graph.py                      # Compiled LangGraph entry point
├── langgraph.json                # LangGraph deployment config
├── pyproject.toml                # Dependencies and project metadata
└── wake_word.py                  # Voice-activation trigger script
```

---

## Setup & Installation

### Prerequisites

- **Python 3.11+**
- **uv** (recommended package manager)
- **macOS** (required for `say` command and `open_mac_app` tool)
- **Local LLM Server**: [Ollama](https://ollama.ai) or [llama.cpp](https://github.com/ggerganov/llama.cpp) running a multimodal model (e.g., LLaVA)

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# LLM backend (Ollama or llama.cpp OpenAI-compatible server)
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
SUPERVISOR_MODEL=multimodal-model

# Swiggy Food Agent (optional — agent starts without these, tools will be empty)
SWIGGY_ACCESS_TOKEN=<your-bearer-token>
SWIGGY_FOOD_MCP_URL=https://mcp.swiggy.com/food   # default, can omit
```

### 3. Start the server

```bash
langgraph dev
```

The LangGraph dev server starts at `http://127.0.0.1:2024`.  
Both graphs are available in LangGraph Studio:
- `agent` — supervisor / multimodal assistant
- `swiggy_food` — Swiggy food ordering assistant

---

## Swiggy MCP Integration

### How it works

`src/tools/swiggy_mcp.py` connects to the Swiggy MCP server at import time:

1. On module load, `asyncio.run()` opens a one-shot MCP handshake to `mcp.swiggy.com/food`
2. All 14 food tools are fetched and returned as standard LangChain `BaseTool` instances
3. These tools are stored in `SWIGGY_FOOD_TOOLS` and bound to the LLM in the food agent
4. When the agent calls a tool, the `ToolNode` executes it — which makes an authenticated HTTP call back to the Swiggy MCP endpoint
5. If the MCP server is unreachable (no token, no network), the list is empty and a warning is logged — the app still starts

### Getting a Swiggy access token

Swiggy MCP uses **OAuth 2.1 with PKCE**:

**1. Apply for access**

Go to `https://mcp.swiggy.com/builders/access/` and apply with your redirect URI and intended scope (`mcp:tools`). You'll receive a `client_id`.

**2. Generate PKCE pair**

```python
import secrets, hashlib, base64

code_verifier = secrets.token_urlsafe(32)
digest = hashlib.sha256(code_verifier.encode()).digest()
code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
```

**3. Redirect user to authorization**

```
https://mcp.swiggy.com/auth/authorize
  ?response_type=code
  &client_id=<your-client-id>
  &redirect_uri=http://localhost:<port>/callback
  &code_challenge=<code_challenge>
  &code_challenge_method=S256
  &scope=mcp:tools
```

**4. Exchange code for token**

```bash
curl -X POST https://mcp.swiggy.com/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "code": "<code>",
    "code_verifier": "<code_verifier>",
    "client_id": "<client_id>",
    "redirect_uri": "http://localhost:<port>/callback"
  }'
```

Response: `{ "access_token": "...", "expires_in": 432000 }` (5-day lifetime)

**5. Set in `.env`**

```env
SWIGGY_ACCESS_TOKEN=<access_token>
```

---

## Usage Examples

### Supervisor Agent

- "What am I holding right now?" — captures webcam and describes the scene
- "How is my battery looking?" — calls `get_system_info`
- "Open Safari" — calls `open_mac_app`
- "Speak your response out loud" — triggers TTS

### Swiggy Food Agent

- "Find me pizza places near Koramangala" — calls `search_restaurants`
- "Show me the menu for Domino's" — calls `get_restaurant_menu`
- "Add a Margherita pizza to my cart" — calls `update_food_cart`
- "Do I have any coupons?" — calls `fetch_food_coupons`
- "Place my order" — shows cart summary, waits for confirmation, then calls `place_food_order`
- "Where is my order?" — calls `track_food_order`

---

## Security Notes

- The UI requires a Bearer token in the settings bar to authorize chat requests.
- Swiggy access tokens have a 5-day lifetime. Treat a 401 response as a signal to re-authenticate.
- Never log or transmit tokens over non-HTTPS connections.
- `SWIGGY_ACCESS_TOKEN` is read from `.env` at startup — ensure `.env` is in `.gitignore`.
