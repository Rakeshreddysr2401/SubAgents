# CLAUDE.md — Developer & AI Reference

Technical reference for the SubAgents codebase. Read this before making changes.

---

## Quick Facts

- **Runtime**: Python 3.11+, managed with `uv`
- **Framework**: LangGraph (graph), FastAPI (API), llama.cpp via OpenAI-compatible API (LLM)
- **Start command**: `langgraph dev` → server at `http://127.0.0.1:2024`
- **Single graph**: `agent` in `langgraph.json` → `graph.py:graph`
- **4 agents**: supervisor (router), conversation, swiggy, tracker

---

## Folder Structure

```
src/
├── agents/          # LLM agent nodes (supervisor, conversation, swiggy, tracker)
├── nodes/           # Utility/routing nodes (turn_entry, handle_handover)
├── tools/           # Tool definitions and MCP loader
├── commons/         # Shared constants (agent name strings)
├── states/          # AgentState TypedDict
├── utils/           # message_utils, frame_buffer
└── configs/         # logging_config, memory_config
```

---

## Graph Architecture

### Entry Point

`graph.py` builds and exports the unified `graph`. Every user turn begins at `turn_entry`.

`turn_entry` resets per-turn state and routes to the supervisor (or a sticky agent if configured). The supervisor calls `handover()` to route to a sub-agent. Sub-agents respond, then call `handover()` when done. `handle_handover` resolves the destination and either chains immediately or sets the next agent for the following turn.

### Node Map

```
START
  └─► turn_entry ──► supervisor ──► supervisor_tools ──┐
                                                        │
                                               handle_handover
                                              (chain → Command(goto=next))
                                              (sticky → dict + END)
                                                        │
         ┌──────────────────────────────────────────────┤
         ▼                              ▼               ▼
    conversation               swiggy               tracker
    conversation_tools         swiggy_tools         tracker_tools
         │                              │               │
         └────────────── (same handle_handover pattern) ┘
```

### Routing Functions (`graph.py`)

**`_route_after_agent(state)`** — runs after every agent LLM call:
- Last message has `tool_calls` → `"tools"` (agent's own tool node)
- No tool calls → `END`

**`_route_after_tools(state, agent_name)`** — runs after every tool node:
- Handover `ToolMessage` found → `"handle_handover"`
- No handover → back to `agent_name` (loop for multi-tool tasks)

---

## Handover System

### `turn_entry` (`src/nodes/turn_entry.py`)

Runs at the start of every user turn. Resets `agent_turn_visits` to `{}` (fixes loop guard accumulation across turns). Routes to supervisor by default; routes directly to a sticky agent if `active_agent` is in `_STICKY_AGENTS`.

### `handle_handover` (`src/nodes/handle_handover.py`)

Single centralized handover resolver. Two outcomes:

**Chain (immediate)** — agent was silent (no AI text) OR `chain=True`:
```python
handover("tracker", reason="order_placed", chain=True)  # next agent responds same turn
handover("swiggy", reason="user wants food")             # supervisor was silent → chains
```
Returns `Command(goto=next_agent)` — next agent responds in the same turn.

**Sticky (deferred)** — agent spoke AND `chain=False`:
```python
handover("supervisor", reason="tracking_done")  # after agent already responded
```
Returns `dict(active_agent=next_agent)` — graph exits to `END`, next agent responds on the next user turn.

### Bridge Messages

Every handover injects a `SystemMessage` into state before routing to the next agent:

```python
# For sub-agents (conversation, swiggy, tracker):
f"You are the {next_agent} agent, responsible for: {desc}.\n"
f"You were called because: \"{reason}\". The user said: \"{user_query}\"."

# When routing back to supervisor:
"Route to the appropriate agent based on the conversation."
# or if cannot_answer:
f"The previous agent ('{current}') could not answer. Do NOT route back to '{current}'."
```

### Loop Guard

Inside `handle_handover`. If any agent is visited more than 3 times in a single turn, it redirects to `conversation` with tools-disabled messaging. `agent_turn_visits` is reset to `{}` on every new turn by `turn_entry`.

### Handover Tool (`src/tools/handover_tool.py`)

```python
@tool("handover")
def handover(
    next_agent: Literal["supervisor", "conversation", "swiggy", "tracker"],
    reason: str = "",
    chain: bool = False,
) -> str:
    return json.dumps({"next_agent": next_agent, "reason": reason, "chain": chain})
```

Returns JSON. Parsed by `parse_handover()` in `src/nodes/handle_handover.py`.

---

## Agent Name Constants (`src/commons/constants.py`)

```python
SUPERVISOR   = "supervisor"
CONVERSATION = "conversation"
SWIGGY       = "swiggy"
TRACKER      = "tracker"

AGENT_DESCRIPTIONS = { ... }  # used by handle_handover for bridge messages
```

Always import from here in code. Inline strings are only acceptable inside LLM prompt text.

---

## State (`src/states/states.py`)

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

Additional runtime state written via `Command(update={...})` or node return dicts:

| Key | Type | Set by | Purpose |
|---|---|---|---|
| `active_agent` | `str` | Each agent node, `handle_handover` | Tracks which agent last responded; included in SSE stream |
| `always_speak` | `bool` | `webapp.py` on input | If true, speak response via TTS |
| `agent_turn_visits` | `dict[str, int]` | `turn_entry` (reset), `handle_handover` (increment) | Loop guard: visit count per agent per turn |

`messages` uses the `add_messages` reducer — it always **appends**, never replaces. This is why message cleaning is needed before LLM calls.

---

## Message Cleaning (`src/utils/message_utils.py`)

Every agent calls `prepare_messages_for_agent(state["messages"])` before invoking the LLM to strip routing noise.

**What gets stripped:**
- `AIMessage` with only `handover` tool_calls and no text — pure routing, invisible to agents
- `ToolMessage` where `msg.name == "handover"` — routing result JSON
- Stale `SystemMessage`s from earlier turns — only the most recent is kept (sub-agents), or all from current turn (supervisor with `keep_all_system_msgs=True`)

**What is preserved:**
- All `HumanMessage`s
- `AIMessage`s with actual text content (agent responses)
- `AIMessage`s with non-handover tool calls (agent's own tool usage)
- `ToolMessage`s from non-handover tools (e.g., Swiggy API results)

---

## Tool Sets (`src/tools/__init__.py`)

```python
SUPERVISOR_TOOLS    = [handover]
CONVERSATION_TOOLS  = [capture_webcam, get_system_info, open_mac_app, *tavily, handover]
SWIGGY_TOOLS        = [*SWIGGY_FOOD_TOOLS, handover]
TRACKER_TOOLS       = [*SWIGGY_FOOD_TOOLS, handover]
```

- `SWIGGY_FOOD_TOOLS` is loaded from the Swiggy MCP server at import time (`swiggy_mcp.py`)
- Swiggy and Tracker share the same MCP tools (one connection, one fetched list)
- Tavily is optional: only added if `langchain-community` is installed and `TAVILY_API_KEY` is set
- `ALL_TOOLS` is a legacy alias for `CONVERSATION_TOOLS`

---

## Agents

### supervisor_agent.py

- **Never produces text** — any text alongside a `handover` call is stripped before returning
- `keep_all_system_msgs=True` when cleaning — sees all bridge messages from current turn
- Binds only `[handover]` as tools

### conversation_agent.py, swiggy_agent.py, tracker_agent.py

All follow the same pattern:
```python
def _build_prompt(state: AgentState) -> str:
    return "..."  # returns system prompt string; receives state for context if needed

def {name}_node(state: AgentState):
    from src.tools import {NAME}_TOOLS          # late import avoids circular deps
    llm_with_tools = llm.bind_tools({NAME}_TOOLS)
    clean_messages = prepare_messages_for_agent(state["messages"])
    response = safe_invoke(llm_with_tools, [SystemMessage(content=_build_prompt(state))] + clean_messages, logger)
    return {"messages": [response], "active_agent": {NAME}}
```

Late import of tools (`from src.tools import ...` inside the function) avoids circular import issues since `tools/__init__.py` imports from `swiggy_mcp.py` which does async work at module load.

---

## LLM Config (`src/llm_config.py`)

```python
llm = ChatOpenAI(
    base_url=os.getenv("LLAMA_CPP_BASE_URL", "http://singireddys-mac-mini.local:8080/v1"),
    api_key="not-needed",
    model=os.getenv("SUPERVISOR_MODEL", "multimodal-model"),
    temperature=0,
)
```

All 4 agents use the same global `llm` instance. The LLM server must be OpenAI-compatible (llama.cpp `--api`, Ollama, etc.).

---

## SSE Stream Format (`src/webapp.py`)

The `/chat` endpoint calls `client.runs.wait()` on the LangGraph SDK, extracts the response, then streams as SSE:

```
data: {"text": "Here are some options...", "active_agent": "swiggy"}\n\n
data: {"done": true, "thread_id": "abc123", "active_agent": "swiggy"}\n\n
```

Both events are JSON. The `active_agent` field tells the UI which agent generated the response.

`_extract_response(result)` finds the last `HumanMessage` in state and collects all `AIMessage` content after it. This ensures only the current turn's responses are shown.

---

## Swiggy MCP (`src/tools/swiggy_mcp.py`)

- Runs at import time via `asyncio.run()` (or thread executor if already in a running loop)
- Uses `MultiServerMCPClient` with `streamable_http` transport
- Call pattern: `client = MultiServerMCPClient({...}); tools = await client.get_tools()`
- Graceful degradation: on any failure, `SWIGGY_FOOD_TOOLS = []` and a warning is logged
- The app always starts regardless of MCP availability

---

## Video Frame Buffer (`src/utils/frame_buffer.py`)

- Thread-safe dict of `{thread_id: latest_base64_jpeg_string}`
- `store_frame(tid, data)` — called by WebSocket handler
- `get_latest_frame(tid)` — called by `capture_webcam` tool
- Lock-based synchronization (`threading.Lock`)

---

## Adding a New Agent

1. **Create `src/agents/{name}_agent.py`** — follow the pattern above (`_build_prompt`, late tool import, return `active_agent` using the constant)
2. **Add constant in `src/commons/constants.py`** — `NAME = "{name}"` and add to `AGENT_DESCRIPTIONS`
3. **Add tool set in `src/tools/__init__.py`** — `{NAME}_TOOLS = [...]`
4. **Register in `graph.py`**:
   - `add_node(NAME, {name}_node)`
   - `add_node(f"{NAME}_tools", ToolNode(tools={NAME}_TOOLS))`
   - `add_conditional_edges(NAME, _route_after_agent, {"tools": f"{NAME}_tools", END: END})`
   - `add_conditional_edges(f"{NAME}_tools", lambda s, a=NAME: _route_after_tools(s, a), {"handle_handover": "handle_handover", NAME: NAME})`
5. **Update supervisor system prompt** with the new agent's name and description
6. **Update `handover_tool.py`** — add `"{name}"` to the `Literal` type

---

## Common Pitfalls

- **Never import `SWIGGY_FOOD_TOOLS` at module level inside agent files** — use late imports inside the node function to avoid circular dependency with `swiggy_mcp.py`'s async load
- **Supervisor must always call `handover()`** — if it doesn't, it goes to `END` silently with no response. Check the system prompt if routing breaks
- **Sticky handover goes to `END`** — when an agent responds and calls `handover(chain=False)`, the next agent only responds on the *next* human message. Use `chain=True` for same-turn chaining
- **Loop guard caps visits at 3** — if an agent is visited more than 3 times in one turn without user input, it breaks to `conversation`. This usually signals a routing loop in the system prompts
