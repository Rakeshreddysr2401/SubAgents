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

## Graph Architecture

### Entry Point

`graph.py` builds and exports the unified `graph`. The entry point is always `START → supervisor`.

Every user turn begins at supervisor. The supervisor calls `handover()` to route to a sub-agent. Sub-agents respond, then call `handover("supervisor")` when done. The supervisor re-routes on the next turn.

### Node Map

```
START
  └─► supervisor ──► supervisor_tools ──┐
                                        │
                             ┌──────────┴──────────────┐
                             │   handover routing      │
                             │  apply_handover         │ ← Command(goto=next)
                             │  respond_then_wait ─► END
                             │  respond_and_chain      │ ← Command(goto=next)
                             └──────────┬──────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────┐
         ▼                              ▼                          ▼
    conversation               swiggy                         tracker
    conversation_tools         swiggy_tools                   tracker_tools
         │                              │                          │
         └──────────── (same handover routing pattern) ───────────┘
```

### Routing Functions (`graph.py`)

**`_route_after_agent(state)`** — runs after every agent LLM call:
- Last message has `tool_calls` → `"tools"` (agent's own tool node)
- No tool calls → `END`

**`_route_after_tools(state, agent_name)`** — runs after every tool node:
- No handover in tool results → back to `agent_name` (loop for multi-tool tasks)
- Handover found, no AI text → `"apply_handover"` (Type 1)
- Handover found, has AI text, `chain=False` → `"respond_then_wait"` (Type 2)
- Handover found, has AI text, `chain=True` → `"respond_and_chain"` (Type 3)

---

## The 3 Handover Types

Defined in `src/agents/handover.py`. Triggered by `_route_after_tools`.

### Type 1 — `apply_handover` (silent transfer)

```python
# Agent calls handover with no response text:
handover("swiggy", reason="user wants to order food")
```

- Current agent produces **no text** — user sees nothing from current agent
- `apply_handover` node resolves next agent, injects a bridging `SystemMessage`, returns `Command(goto=next_agent)`
- Next agent responds immediately in the same turn
- **Loop guard runs here**: if `agent_turn_visits[next_agent] > 3`, breaks to `conversation` agent

### Type 2 — `respond_then_wait`

```python
# Agent responds with text, then calls handover:
handover("supervisor", reason="tracking_done")  # after AI text already in response
```

- Current agent **has already responded** with text
- `respond_then_wait` prepends that `AIMessage` to state, sets `active_agent`, returns `dict` (no Command)
- Graph exits to `END` — next agent picks up on the **next human turn**

### Type 3 — `respond_and_chain`

```python
# swiggy_agent places order, says "Order placed!", then:
handover("tracker", reason="order_placed", chain=True)
```

- Current agent responds with text **AND** next agent responds immediately after
- `respond_and_chain` prepends `AIMessage` + bridge, returns `Command(goto=next_agent)`
- Both agents' responses appear in the **same turn** to the user

### Bridge Messages

Every handover injects a `SystemMessage` into state before routing to the next agent. Content:

```python
# For sub-agents (conversation, swiggy, tracker):
f"You are the {next_agent} agent, responsible for: {desc}.\n"
f"You were called because: \"{reason}\". The user said: \"{user_query}\"."

# When routing back to supervisor:
"Route to the appropriate agent based on the conversation."
# or if cannot_answer:
f"The previous agent ('{current}') could not answer. Do NOT route back to '{current}'."
```

### Sub-Agent Adapter

Sub-agents (conversation, swiggy, tracker) can **only** route to `"supervisor"`. If a sub-agent tries to route to another sub-agent, `_resolve_handover` overrides the destination to `"supervisor"`.

---

## State (`src/states/states.py`)

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

Additional runtime state is written via `Command(update={...})` or node return dicts:

| Key | Type | Set by | Purpose |
|---|---|---|---|
| `active_agent` | `str` | Each agent node, handover handlers | Tracks which agent last responded; included in SSE stream |
| `always_speak` | `bool` | webapp.py on input | If true, speak response via TTS |
| `agent_turn_visits` | `dict[str, int]` | `apply_handover` | Loop guard: visit count per agent per turn |

`messages` uses the `add_messages` reducer — it always **appends**, never replaces. This is why message cleaning is needed before LLM calls.

---

## Message Cleaning (`src/utils/message_utils.py`)

Every agent calls `prepare_messages_for_agent(state["messages"])` before invoking the LLM to strip routing noise.

**What gets stripped:**
- `AIMessage` with only `handover` tool_calls and no text — pure routing, invisible to agents
- `ToolMessage` where `msg.name == "handover"` — routing result (`"swiggy|order food|false"`)
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
def {name}_node(state: AgentState):
    from src.tools import {NAME}_TOOLS          # late import avoids circular deps
    llm_with_tools = llm.bind_tools({NAME}_TOOLS)
    clean_messages = prepare_messages_for_agent(state["messages"])
    response = safe_invoke(llm_with_tools, [SystemMessage(content=_SYSTEM_PROMPT)] + clean_messages, logger)
    return {"messages": [response], "active_agent": "{name}"}
```

Late import of tools (`from src.tools import ...` inside the function) avoids circular import issues since `tools/__init__.py` imports from `swiggy_mcp.py` which does async work at module load.

---

## Handover Tool (`src/tools/handover_tool.py`)

```python
@tool("handover")
def handover(
    next_agent: Literal["supervisor", "conversation", "swiggy", "tracker"],
    reason: str = "",
    chain: bool = False,
) -> str:
    return f"{next_agent}|{reason}|{str(chain).lower()}"
```

The return value is a pipe-delimited string parsed by `parse_handover()` in `handover.py`. `chain=True` triggers Type 3 (respond_and_chain); `chain=False` (default) triggers Type 2 if there's AI text, Type 1 if not.

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

1. **Create `src/agents/{name}_agent.py`** — follow the pattern above (system prompt, late tool import, return `active_agent`)
2. **Add tool set in `src/tools/__init__.py`** — `{NAME}_TOOLS = [...]`
3. **Register in `graph.py`**:
   - `add_node("{name}", {name}_node)`
   - `add_node("{name}_tools", ToolNode(tools={NAME}_TOOLS))`
   - `add_conditional_edges("{name}", _route_after_agent, {"tools": "{name}_tools", END: END})`
   - `add_conditional_edges("{name}_tools", lambda s: _route_after_tools(s, "{name}"), {**_HANDOVER_ROUTES, "{name}": "{name}"})`
4. **Update supervisor system prompt** with the new agent's name and description
5. **Update `handover_tool.py`** — add `"{name}"` to the `Literal` type
6. **Update `handover.py`** — add description to `_AGENT_DESCRIPTIONS` and to `SUB_AGENTS` set

---

## Common Pitfalls

- **Never import `SWIGGY_FOOD_TOOLS` at module level inside agent files** — use late imports inside the node function to avoid circular dependency with `swiggy_mcp.py`'s async load
- **Supervisor must always call `handover()`** — if it doesn't, it goes to `END` silently with no response. Check the system prompt if routing breaks
- **`respond_then_wait` goes to `END`** — the next agent only responds on the *next* human message, not immediately. Use `chain=True` for same-turn chaining
- **Loop guard caps visits at 3** — if an agent is visited more than 3 times in one turn without user input, it breaks to `conversation`. This usually signals a routing loop in the system prompts
- **`agent_turn_visits` is not reset between user turns automatically** — it accumulates unless the graph checkpointer starts a fresh state per turn (MemorySaver preserves across turns)
