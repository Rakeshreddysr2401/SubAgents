"""POST /chat — run the graph in-process and stream tokens over SSE.

SSE contract (each event is a JSON object on a `data:` line):
  {"delta": "<token>"}                                  0..n times
  {"done": true, "thread_id": ..., "active_agent": ...} exactly once on success
  {"error": "<message>"}                                on failure
The legacy {"text": ...} full-response event is no longer emitted; the
frontend handles both shapes.
"""

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

from src.api.auth import get_user_id
from src.api.deps import validate_thread_id
from src.commons.constants import CONVERSATION, SWIGGY, TRACKER
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.memory.post_turn import run_post_turn
from src.models.schema import ChatRequest
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


_AGENT_NODES = {CONVERSATION, SWIGGY, TRACKER}


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


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    thread_id: str = Query(default=None),
    user_id: str = Depends(get_user_id),
):
    settings = get_settings()
    await enforce_rate_limit("chat", user_id)
    tid = validate_thread_id(thread_id or str(uuid4()))
    graph = request.app.state.graph
    await request.app.state.thread_store.touch(tid, user_id, req.query[:FIRST_MESSAGE_MAX_CHARS])
    config = {"configurable": {"thread_id": tid, "user_id": user_id}}
    inputs = {
        "messages": [HumanMessage(content=req.query)],
        "always_speak": req.always_speak,
        "agent_turn_visits": {},
    }
    logger.info("Chat request: thread=%s, query=%s", tid, req.query[:80])

    async def event_generator():
        full: list[str] = []
        active_agent = CONVERSATION
        try:
            async with asyncio.timeout(settings.chat_timeout_seconds):
                async for item in graph.astream(
                    inputs, config, stream_mode=["messages", "updates"], subgraphs=True
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
                        agent = _extract_active_agent(payload)
                        if agent:
                            active_agent = agent
        except (TimeoutError, asyncio.TimeoutError):
            logger.error("Graph execution timed out for thread=%s", tid)
            yield _sse({"error": "Request timed out"})
            return
        except Exception as e:
            logger.exception("Streaming chat failed for thread=%s", tid)
            yield _sse({"error": str(e)})
            return

        full_text = "".join(full)
        if req.always_speak and full_text:
            background_tasks.add_task(speak_out_loud, full_text)
        # Runs after the response completes: Mem0 write + history/vision indexing.
        # BackgroundTasks (not a bare create_task) so it isn't GC'd/cancelled.
        background_tasks.add_task(run_post_turn, request.app, tid, user_id)
        yield _sse({"done": True, "thread_id": tid, "active_agent": active_agent})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
