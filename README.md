# SubAgents — Multi-Agent AI Desktop Assistant

A locally-run, multimodal AI assistant built on **LangGraph**, **FastAPI**, and **llama.cpp / Ollama**. Multiple specialized agents collaborate through structured handovers to handle general queries, food ordering, and delivery tracking — without losing conversational context between agents.

---

## Key Features

- **Multi-Agent Coordination** — 4 agents with typed handover: supervisor (router), conversation, swiggy, tracker
- **Multimodal Perception** — live webcam vision via the conversation agent
- **Food Ordering** — Swiggy MCP integration: search restaurants, manage cart, place and track orders
- **Web Search** — Tavily-powered real-time search in the conversation agent
- **Conversational Voice** — optional TTS via macOS `say` command
- **Persistent Memory** — conversation history across turns via LangGraph checkpointers
- **Local-First** — runs with local LLMs (LLaVA, Gemma, etc.) via llama.cpp or Ollama

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      Frontend (UI)                       │
│  HTML/JS SPA ──SSE──► /chat  (JSON stream)               │
│              ──WS──►  /ws/frames  (video frames)         │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP / WebSocket
┌───────────────────────────▼──────────────────────────────┐
│                    FastAPI (webapp.py)                    │
│  /chat  /history  /events  /ws/frames  /trigger_voice    │
└───────────────────────────┬──────────────────────────────┘
                            │ LangGraph SDK
┌───────────────────────────▼──────────────────────────────┐
│                  LangGraph Server (graph: "agent")        │
│                                                          │
│   START ──► supervisor (router)                          │
│                  │                                       │
│          ┌───────┴──────────┐                            │
│          ▼                  ▼                            │
│     conversation          swiggy ──► tracker             │
│    (general + vision)   (ordering)  (tracking)           │
│                                                          │
│   Handover types: apply_handover │ respond_then_wait     │
│                   respond_and_chain                      │
└──────────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Responsibility | Tools |
|---|---|---|
| **supervisor** | Pure router — decides which agent handles each request | `handover` |
| **conversation** | General queries, web search, webcam vision, system info | `capture_webcam`, `get_system_info`, `open_mac_app`, `tavily_search`*, `handover` |
| **swiggy** | Food ordering: search, cart, place orders | 14 Swiggy MCP tools, `handover` |
| **tracker** | Order status and live delivery tracking | Swiggy MCP tools, `handover` |

*Requires `TAVILY_API_KEY`

### The 3 Handover Types

```
Type 1 — apply_handover
  Current agent:  (no text) ──► next agent responds immediately
  Use when:       supervisor routes silently to a sub-agent

Type 2 — respond_then_wait
  Current agent:  "Here's my answer" ──► END
  Next agent:     picks up on the next human turn
  Use when:       agent finishes and hands context to supervisor

Type 3 — respond_and_chain
  Current agent:  "Order placed!" ──► next agent responds immediately
  Use when:       swiggy places an order → tracker immediately checks status
```

---

## Project Structure

```
SubAgents/
├── graph.py                      # Unified LangGraph entry point (all 4 agents)
├── langgraph.json                # LangGraph deployment config
├── pyproject.toml
├── wake_word.py                  # Voice-activation trigger script
├── static/
│   └── index.html                # Web chat UI
└── src/
    ├── agents/
    │   ├── supervisor_agent.py   # Pure router — calls handover(), never responds
    │   ├── conversation_agent.py # General queries, vision, web search
    │   ├── swiggy_agent.py       # Food ordering
    │   ├── tracker_agent.py      # Order tracking
    │   └── handover.py           # 3 handover handler nodes + loop guard
    ├── configs/
    │   ├── logging_config.py
    │   └── memory_config.py      # MemorySaver checkpointer
    ├── models/
    │   └── schema.py             # ChatRequest / ChatResponse schemas
    ├── states/
    │   └── states.py             # AgentState TypedDict
    ├── tools/
    │   ├── __init__.py           # Per-agent tool sets
    │   ├── handover_tool.py      # handover() routing tool
    │   ├── vision_tools.py       # capture_webcam
    │   ├── audio_tools.py        # speak_out_loud utility
    │   ├── system_tools.py       # get_system_info, open_mac_app
    │   └── swiggy_mcp.py         # Swiggy MCP client → SWIGGY_FOOD_TOOLS
    ├── utils/
    │   ├── frame_buffer.py       # Thread-safe in-memory frame buffer
    │   └── message_utils.py      # Strip handover noise before LLM calls
    ├── llm_config.py             # LLM setup (llama.cpp / Ollama)
    └── webapp.py                 # FastAPI + SSE + WebSocket server
```

---

## Setup & Installation

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- macOS (required for `say` TTS and `open_mac_app`)
- Local LLM server: [Ollama](https://ollama.ai) or [llama.cpp](https://github.com/ggerganov/llama.cpp) running a multimodal model (e.g., LLaVA)

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# LLM backend — llama.cpp or Ollama (OpenAI-compatible endpoint)
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
SUPERVISOR_MODEL=multimodal-model

# Swiggy Food Agent (optional — app starts without these, swiggy/tracker tools will be empty)
SWIGGY_ACCESS_TOKEN=<your-bearer-token>
SWIGGY_FOOD_MCP_URL=https://mcp.swiggy.com/food

# Web search for conversation agent (optional)
TAVILY_API_KEY=<your-tavily-key>
```

### 3. Start the server

```bash
langgraph dev
```

The LangGraph dev server starts at `http://127.0.0.1:2024`.  
The unified `agent` graph is available in LangGraph Studio.

---

## Environment Variables

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `LLAMA_CPP_BASE_URL` | `http://singireddys-mac-mini.local:8080/v1` | Yes | LLM server base URL |
| `SUPERVISOR_MODEL` | `multimodal-model` | Yes | Model name loaded on LLM server |
| `SWIGGY_ACCESS_TOKEN` | *(empty)* | No | Bearer token for Swiggy MCP |
| `SWIGGY_FOOD_MCP_URL` | `https://mcp.swiggy.com/food` | No | Swiggy MCP endpoint |
| `TAVILY_API_KEY` | *(empty)* | No | Tavily web search API key |

---

## API Reference

### POST /chat

Send a message and stream the response.

**Request:**
```json
{ "query": "find me pizza near Koramangala", "always_speak": false }
```

**Response** (Server-Sent Events stream):
```
data: {"text": "Here are some pizza places...", "active_agent": "swiggy"}\n\n
data: {"done": true, "thread_id": "abc123", "active_agent": "swiggy"}\n\n
```

Each SSE event is valid JSON. Read `active_agent` to know which agent generated the response.

**Query param:** `?thread_id=<id>` — pass to continue an existing conversation. A new UUID is generated if omitted.

### WebSocket /ws/frames

Stream video frames for webcam vision.

**Query param:** `?thread_id=<id>`  
**Message format:** Base64-encoded JPEG as text, or raw bytes (binary path for Jetson).  
The latest frame per thread is stored in memory and used when the conversation agent calls `capture_webcam`.

### GET /history/{thread_id}

Returns conversation history for a thread.

```json
{ "thread_id": "abc123", "messages": [{"role": "user", "content": "..."}, ...] }
```

### GET /health

```json
{ "status": "ok", "service": "owp-agent" }
```

### GET /events

SSE stream for wake-word triggers. Yields `"start_voice"` when the wake word fires.

### POST /trigger_voice

Called by `wake_word.py`. Pushes a `"start_voice"` event to all `/events` listeners.

---

## Usage Examples

### Conversation agent (general queries)

```
"What's the weather like in Bangalore today?"   → web search via Tavily
"What am I holding right now?"                  → captures webcam, describes scene
"What time is it and how's my battery?"         → get_system_info
"Open Safari"                                   → open_mac_app
"Tell me a joke"                                → direct response
```

### Swiggy agent (food ordering)

```
"Find pizza places near Koramangala"            → search_restaurants
"Show me Domino's menu"                         → get_restaurant_menu
"Add a Margherita pizza to my cart"             → update_food_cart
"Do I have any coupons I can use?"              → fetch_food_coupons
"Place my order" (after confirming cart)        → place_food_order → chains to tracker
```

### Tracker agent (order tracking)

```
"Where is my order?"                            → track_food_order
"Show me my recent orders"                      → get_food_orders
"What's the ETA for order #12345?"              → get_food_order_details
```

The tracker is also automatically chained after a successful order placement — it responds in the same turn without any user prompt.

---

## Swiggy MCP Integration

`src/tools/swiggy_mcp.py` loads tools at import time:

1. On module load, opens a one-shot MCP handshake to `mcp.swiggy.com/food`
2. Fetches ~14 food tools as standard LangChain `BaseTool` instances
3. Tools are shared between `swiggy_agent` and `tracker_agent`
4. If the MCP server is unreachable (no token, no network), tools list is empty and a warning is logged — the app still starts

### Getting a Swiggy access token (OAuth 2.1 with PKCE)

**1. Apply for access** at `https://mcp.swiggy.com/builders/access/` — you'll receive a `client_id`.

**2. Generate PKCE pair:**

```python
import secrets, hashlib, base64

code_verifier = secrets.token_urlsafe(32)
digest = hashlib.sha256(code_verifier.encode()).digest()
code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
```

**3. Redirect user to authorization:**

```
https://mcp.swiggy.com/auth/authorize
  ?response_type=code
  &client_id=<your-client-id>
  &redirect_uri=http://localhost:<port>/callback
  &code_challenge=<code_challenge>
  &code_challenge_method=S256
  &scope=mcp:tools
```

**4. Exchange code for token:**

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

**5.** Set `SWIGGY_ACCESS_TOKEN=<access_token>` in `.env`.

---

## Security Notes

- `SWIGGY_ACCESS_TOKEN` has a 5-day lifetime. A 401 response means re-authentication is needed.
- Never commit `.env` to version control — it's in `.gitignore`.
- Never transmit tokens over non-HTTPS connections.
- The LLM server (`LLAMA_CPP_BASE_URL`) should only be accessible on your local network.
