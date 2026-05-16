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
LLAMA_CPP_BASE_URL=http://localhost:11434/v1
SUPERVISOR_MODEL=llava
```

No Swiggy env vars needed — auth is handled via the browser OAuth flow below.

### 3. Authenticate with your Swiggy account (once)

```bash
python auth_swiggy.py
```

This opens a browser window. Log in with your Swiggy account. After login you'll see:

```
✓ Authenticated! 14 food tools available:
  search_restaurants             Find restaurants...
  get_restaurant_menu            Access complete menu...
  ...
Token saved to .swiggy_tokens_food.json
```

The token lasts 5 days. Re-run `auth_swiggy.py` when it expires.

> **No Swiggy developer registration needed.** The client ID `swiggy-mcp` is the public MCP client
> ID that Swiggy exposes for all MCP integrations — just log in with your own account.

### 4. Start the LangGraph server

```bash
langgraph dev
```

The LangGraph dev server starts at `http://127.0.0.1:2024`.  
Both graphs are available in LangGraph Studio:
- `agent` — supervisor / multimodal assistant
- `swiggy_food` — Swiggy food ordering assistant (uses your real Swiggy account)

---

## Swiggy MCP Integration

### How it works

```
auth_swiggy.py   →  browser login  →  .swiggy_tokens_food.json
                                              ↓
langgraph dev  →  first swiggy_food message
                        ↓
              SwiggyMCPClient.session()  (loads saved token)
                        ↓
              load_mcp_tools(session)   (fetches all 14 tool definitions)
                        ↓
              LLM bound to 14 tools  →  tool calls  →  real Swiggy API
```

Key design decisions:
- **OAuth 2.1 via `mcp` SDK** — `OAuthClientProvider` handles PKCE, token exchange, and refresh automatically
- **Lazy session init** — MCP session opens on the first agent invocation, not at server startup
- **Persistent session** — the session stays open for the process lifetime so tools can be reused cheaply
- **Dynamic tool loading** — `load_mcp_tools(session)` fetches live tool definitions from Swiggy, so new tools appear automatically without code changes
- **Token persistence** — saved to `.swiggy_tokens_food.json`; re-auth only needed when token expires

### Local mock (offline development)

A fully local mock MCP server is available for development without Swiggy credentials:

```bash
# Terminal 1 — start mock
python src/mock/swiggy_mock_mcp.py

# Terminal 2 — start LangGraph (no auth_swiggy.py needed)
langgraph dev
```

The mock has 4 Bangalore restaurants, a stateful cart, orders, and coupons — all 14 food tools.

---

## Usage Examples

### Supervisor Agent

- "What am I holding right now?" — captures webcam and describes the scene
- "How is my battery looking?" — calls `get_system_info`
- "Open Safari" — calls `open_mac_app`

### Swiggy Food Agent (real account)

- "Find me pizza places near Koramangala" — calls `search_restaurants`
- "Show me the menu for Domino's" — calls `get_restaurant_menu`
- "Add a Margherita pizza to my cart" — calls `update_food_cart`
- "Do I have any coupons?" — calls `fetch_food_coupons`
- "Place my order" — shows cart summary, waits for confirmation, then calls `place_food_order`
- "Where is my order?" — calls `track_food_order`

---

## Security Notes

- Swiggy tokens are saved to `.swiggy_tokens_food.json` — ensure this file is in `.gitignore`
- Tokens have a 5-day lifetime; re-run `auth_swiggy.py` when expired
- The UI requires a Bearer token in the settings bar to authorize LangGraph chat requests
