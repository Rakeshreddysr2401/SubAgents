"""POST /chat — run the graph in-process and stream tokens over SSE.

SSE contract (each event is a JSON object on a `data:` line):
  {"delta": "<token>"}                                    0..n times
  {"agent": "<name>"}                                     0..n times, on active-agent change
  {"tool_call": {"id","name","args","agent"}}              0..n times
  {"tool_result": {"id","name","result_preview","agent"}}  0..n times
  {"interrupt": {"id","action_requests","review_configs"}} 0..n times — a gated
                                                            tool call is awaiting
                                                            approval; no `done`
                                                            follows in this turn,
                                                            call POST /chat/resume
  {"done": true, "thread_id": ..., "active_agent": ...}   exactly once on success
  {"error": "<message>"}                                  on failure
The legacy {"text": ...} full-response event is no longer emitted; the
frontend handles both shapes. `agent`/`tool_call`/`tool_result`/`interrupt`
are additive — older clients that only understand delta/done/error safely
ignore them.
"""

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.api.auth import get_user_id
from src.api.deps import validate_thread_id
from src.commons.constants import CONVERSATION, DINEOUT, INSTAMART, PLANNER, SWIGGY, TRACKER
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.memory.post_turn import run_post_turn
from src.models.schema import ChatRequest, ResumeRequest
from src.services.mcp_providers import refresh_tokens_if_changed
from src.services.rate_limit import enforce_rate_limit
from src.tools.audio_tools import speak_out_loud

FIRST_MESSAGE_MAX_CHARS = 500

logger = get_logger(__name__)
router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _chunk_text(content) -> str:
    """Extract plain text from a message chunk's content (str or block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def _stream_text(chunk, meta: dict) -> str:
    """Return the streamable text of an LLM chunk, or "" if it must be filtered.

    Filtered out: non-AI chunks, tool-call deltas, anything produced by tool nodes.
    """
    # AIMessageChunk (token deltas) is a subclass of AIMessage (whole messages
    # from non-streaming models) — accept both.
    if not isinstance(chunk, AIMessage):
        return ""
    if getattr(chunk, "tool_call_chunks", None) or getattr(chunk, "tool_calls", None):
        return ""
    node = (meta or {}).get("langgraph_node", "")
    if node.endswith("_tools") or node == "tools":
        return ""
    return _chunk_text(chunk.content)


_AGENT_NODES = {CONVERSATION, SWIGGY, INSTAMART, DINEOUT, TRACKER, PLANNER}


def _extract_active_agent(update_payload) -> str | None:
    """Determine the active agent from an `updates` stream payload ({node: update}).

    Two signals: an explicit `active_agent` set by a handoff tool, or the name
    of the agent node that just produced output (covers the sticky case where
    no handoff fires).
    """
    if not isinstance(update_payload, dict):
        return None
    for node, update in update_payload.items():
        if isinstance(update, dict) and update.get("active_agent"):
            return update["active_agent"]
    for node in update_payload:
        if node in _AGENT_NODES:
            return node
    return None


def _is_handoff_tool(name: str | None) -> bool:
    return bool(name) and name.startswith("transfer_to_")


def _extract_tool_calls(update_payload, agent: str) -> list[dict]:
    """Find AIMessage tool_calls newly added by an `updates` payload.

    Handoff tools (transfer_to_*) are excluded — the `agent` event already
    surfaces those transitions.
    """
    if not isinstance(update_payload, dict):
        return []
    events = []
    for update in update_payload.values():
        if not isinstance(update, dict):
            continue
        for msg in update.get("messages") or []:
            for tc in getattr(msg, "tool_calls", None) or []:
                name = tc.get("name")
                if _is_handoff_tool(name):
                    continue
                events.append({"id": tc.get("id"), "name": name, "args": tc.get("args"), "agent": agent})
    return events


def _extract_tool_results(update_payload, agent: str) -> list[dict]:
    """Find ToolMessage results newly added by an `updates` payload."""
    if not isinstance(update_payload, dict):
        return []
    events = []
    for update in update_payload.values():
        if not isinstance(update, dict):
            continue
        for msg in update.get("messages") or []:
            if not isinstance(msg, ToolMessage) or _is_handoff_tool(msg.name):
                continue
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            events.append({
                "id": msg.tool_call_id,
                "name": msg.name,
                "result_preview": content[:500],
                "agent": agent,
            })
    return events


def _stream_graph_events(
    app,
    graph_input,
    config: dict,
    tid: str,
    user_id: str,
    background_tasks: BackgroundTasks,
    always_speak: bool,
):
    """Shared SSE event generator for both /chat and /chat/resume.

    `graph_input` is either the normal `{"messages": [...], ...}` dict (fresh
    turn) or a `Command(resume=...)` (resuming an interrupted turn) — both are
    valid first arguments to `graph.astream`.
    """
    settings = get_settings()
    graph = app.state.graph

    async def event_generator():
        full: list[str] = []
        active_agent = CONVERSATION
        # `updates` fires once per graph level (parent -> swarm -> react agent,
        # subgraphs=True), so the same tool call/result/interrupt would
        # otherwise be re-emitted up to 3x as it bubbles up. Dedup by id.
        seen_tool_calls: set[str] = set()
        seen_tool_results: set[str] = set()
        seen_interrupts: set[str] = set()
        try:
            async with asyncio.timeout(settings.chat_timeout_seconds):
                async for item in graph.astream(
                    graph_input, config, stream_mode=["messages", "updates"], subgraphs=True
                ):
                    # With list stream_mode + subgraphs=True: (namespace, mode, payload)
                    if len(item) == 3:
                        _, mode, payload = item
                    else:
                        mode, payload = item
                    if mode == "messages":
                        chunk, meta = payload
                        text = _stream_text(chunk, meta)
                        if text:
                            full.append(text)
                            yield _sse({"delta": text})
                    elif mode == "updates":
                        interrupts = payload.get("__interrupt__") if isinstance(payload, dict) else None
                        if interrupts:
                            for i in interrupts:
                                if i.id in seen_interrupts:
                                    continue
                                seen_interrupts.add(i.id)
                                yield _sse({"interrupt": {"id": i.id, **i.value}})
                            continue
                        agent = _extract_active_agent(payload)
                        if agent and agent != active_agent:
                            active_agent = agent
                            yield _sse({"agent": active_agent})
                        elif agent:
                            active_agent = agent
                        for tc in _extract_tool_calls(payload, active_agent):
                            if tc["id"] in seen_tool_calls:
                                continue
                            seen_tool_calls.add(tc["id"])
                            yield _sse({"tool_call": tc})
                        for tr in _extract_tool_results(payload, active_agent):
                            if tr["id"] in seen_tool_results:
                                continue
                            seen_tool_results.add(tr["id"])
                            yield _sse({"tool_result": tr})
        except (TimeoutError, asyncio.TimeoutError):
            logger.error("Graph execution timed out for thread=%s", tid)
            yield _sse({"error": "Request timed out"})
            return
        except Exception as e:
            logger.exception("Streaming chat failed for thread=%s", tid)
            yield _sse({"error": str(e)})
            return

        if seen_interrupts:
            # Turn paused for approval: no `done`, no post-turn background
            # work (Mem0/history) yet — the client must POST /chat/resume.
            return

        full_text = "".join(full)
        # Browser voice is handled client-side (speechSynthesis on `done`);
        # the host Mac's `say` is opt-in for the server box only.
        if always_speak and full_text and settings.host_tts_enabled:
            background_tasks.add_task(speak_out_loud, full_text)
        # Runs after the response completes: Mem0 write + history/vision indexing.
        # BackgroundTasks (not a bare create_task) so it isn't GC'd/cancelled.
        background_tasks.add_task(run_post_turn, app, tid, user_id)
        yield _sse({"done": True, "thread_id": tid, "active_agent": active_agent})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    thread_id: str = Query(default=None),
    user_id: str = Depends(get_user_id),
):
    await enforce_rate_limit("chat", user_id)
    # Pick up a Swiggy re-login without restarting (one os.stat; headers
    # stay stable within the turn).
    refresh_tokens_if_changed()
    tid = validate_thread_id(thread_id or str(uuid4()))
    await request.app.state.thread_store.touch(tid, user_id, req.query[:FIRST_MESSAGE_MAX_CHARS])
    config = {
        "configurable": {
            "thread_id": tid,
            "user_id": user_id,
            # Browser geolocation (if granted) — read by get_current_location.
            "location": req.location.model_dump() if req.location else None,
        }
    }
    inputs = {
        "messages": [HumanMessage(content=req.query)],
        "always_speak": req.always_speak,
        "agent_turn_visits": {},
    }
    logger.info("Chat request: thread=%s, query=%s", tid, req.query[:80])
    return _stream_graph_events(
        request.app, inputs, config, tid, user_id, background_tasks, req.always_speak
    )


@router.post("/chat/resume")
async def chat_resume(
    req: ResumeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    thread_id: str = Query(...),
    user_id: str = Depends(get_user_id),
):
    """Resume a turn paused on an `{"interrupt": ...}` SSE event.

    Reuses the same thread_id/config as the original /chat call so LangGraph
    resumes the persisted checkpoint at the interrupted node, three subgraph
    levels deep (parent -> swarm -> react agent) — verified in the Phase 7-8
    HITL spike that this just works via Command(resume=...) with no special
    handling for the nesting.
    """
    await enforce_rate_limit("chat", user_id)
    refresh_tokens_if_changed()
    tid = validate_thread_id(thread_id)
    thread = await request.app.state.thread_store.get(tid)
    if thread is None or thread.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    config = {"configurable": {"thread_id": tid, "user_id": user_id}}
    resume_command = Command(resume={"decisions": [d.model_dump() for d in req.decisions]})
    logger.info("Chat resume: thread=%s, decisions=%d", tid, len(req.decisions))
    return _stream_graph_events(
        request.app, resume_command, config, tid, user_id, background_tasks, req.always_speak
    )


async def read_graph_messages(graph, thread_id: str) -> list[dict]:
    """Extract the {role, content} turn history from the graph's checkpoint state."""
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    except Exception:
        return []

    values = snapshot.values if snapshot else None
    if not values:
        return []

    history = []
    for msg in values.get("messages", []):
        role = getattr(msg, "type", "")
        content = getattr(msg, "content", "")
        if role in ("human", "ai") and content and isinstance(content, str):
            history.append({"role": role, "content": content})
    return history


@router.get("/history/{thread_id}")
async def get_history(thread_id: str, request: Request, user_id: str = Depends(get_user_id)):
    """Conversation history straight from the in-process graph state.

    Gated to the thread's owner via chat_threads metadata.
    """
    tid = validate_thread_id(thread_id)
    thread = await request.app.state.thread_store.get(tid)
    if thread is None or thread.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = await read_graph_messages(request.app.state.graph, tid)
    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"thread_id": tid, "messages": messages}
