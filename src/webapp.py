"""
Custom FastAPI webapp integrated with LangGraph Server.
Mounted into the LangGraph runtime via langgraph.json -> http.app.

Routes:
  GET  /         -> Chat UI (static/index.html)
  POST /chat     -> Send message, get response (SSE stream)
  GET  /health   -> Health check
  GET  /history/{thread_id} -> Conversation history (from LangGraph thread state)
"""
import json
import asyncio
from uuid import uuid4, UUID
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from langgraph_sdk import get_client
from src.configs.logging_config import get_logger
from src.models.schema import ChatRequest, ChatResponse
from src.utils.frame_buffer import store_frame
from src.tools.audio_tools import speak_out_loud

from sse_starlette.sse import EventSourceResponse

logger = get_logger(__name__)

# Queue for sending events to the UI
_event_queue = asyncio.Queue()

# Lazy-initialised SDK client (reuses connection pool)
_client = None

_GRAPH_TIMEOUT_SECONDS = 120.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hook."""
    logger.info("SubAgents started — Multimodal mode active")
    yield
    logger.info("SubAgents stopped")


def _get_client():
    """Get LangGraph SDK client pointing to the local LangGraph Server."""
    global _client
    if _client is None:
        _client = get_client(url="http://127.0.0.1:2024")
    return _client


def _validate_thread_id(tid: str) -> str:
    """Accept UUID format or any string up to 64 chars; reject everything else."""
    try:
        return str(UUID(tid))
    except ValueError:
        pass
    if len(tid) > 64:
        raise HTTPException(status_code=400, detail="Invalid thread_id: too long")
    return tid


app = FastAPI(title="SubAgents API", version="0.1.0", lifespan=lifespan)

# NOTE: No CORS middleware here — LangGraph Server handles CORS for all routes.

# Static files for chat UI
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Serve the built-in chat UI."""
    if _STATIC_DIR.exists() and (_STATIC_DIR / "index.html").exists():
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return "<h1>SubAgents API</h1><p>Chat UI not found. Add static/index.html</p>"


@app.post("/chat")
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    thread_id: str = Query(default=None),
):
    """
    Send a message and stream the response via SSE.
    Uses LangGraph SDK client.runs.wait() with a timeout.
    """
    tid = _validate_thread_id(thread_id or str(uuid4()))
    client = _get_client()
    logger.info("Chat request: thread=%s, query=%s", tid, request.query[:80])

    async def event_generator():
        try:
            await _ensure_thread(client, tid)

            try:
                result = await asyncio.wait_for(
                    client.runs.wait(
                        thread_id=tid,
                        assistant_id="agent",
                        input={
                            "messages": [{"role": "user", "content": request.query}],
                            "always_speak": request.always_speak,
                        },
                    ),
                    timeout=_GRAPH_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error("Graph execution timed out for thread=%s", tid)
                yield f"data: {json.dumps({'error': 'Request timed out'})}\n\n"
                return

            full_response = _extract_response(result)
            active_agent = result.get("active_agent", "conversation") if isinstance(result, dict) else "conversation"

            if full_response:
                payload = json.dumps({"text": full_response, "active_agent": active_agent})
                yield f"data: {payload}\n\n"

                if request.always_speak:
                    background_tasks.add_task(speak_out_loud, full_response)

            yield f"data: {json.dumps({'done': True, 'thread_id': tid, 'active_agent': active_agent})}\n\n"

        except Exception as e:
            logger.error("Streaming chat failed: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.websocket("/ws/frames")
async def video_frame_ws(ws: WebSocket, thread_id: str = Query(default=None)):
    """Receive video frames from the browser (text/base64) or Jetson (binary)."""
    await ws.accept()
    tid = thread_id or "default"
    logger.info("Video WebSocket connected: thread=%s", tid)

    try:
        while True:
            message = await ws.receive()
            if "bytes" in message:
                import base64
                data = base64.b64encode(message["bytes"]).decode("utf-8")
                store_frame(tid, data)
            elif "text" in message:
                store_frame(tid, message["text"])
    except WebSocketDisconnect:
        logger.info("Video WebSocket disconnected: thread=%s", tid)
    except Exception as e:
        logger.warning("Video WebSocket error: thread=%s, err=%s", tid, e)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "subagents"}


@app.get("/history/{thread_id}")
async def get_history(thread_id: str):
    """Get conversation history for a thread from LangGraph thread state."""
    tid = _validate_thread_id(thread_id)
    client = _get_client()
    try:
        state = await client.threads.get_state(thread_id=tid)
    except Exception:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = state.values.get("messages", []) if state and state.values else []
    history = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("type", "unknown")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "unknown")
            content = getattr(msg, "content", "")
        if role in ("human", "user", "ai") and content:
            history.append({"role": role, "content": content})

    return {"thread_id": tid, "messages": history}


@app.get("/events")
async def events(request: Request):
    """Event stream for waking up the browser UI."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.wait_for(_event_queue.get(), timeout=5.0)
                yield {"data": data}
            except asyncio.TimeoutError:
                yield {"comment": "heartbeat"}
    return EventSourceResponse(event_generator())


@app.post("/trigger_voice")
async def trigger_voice():
    """Endpoint for the wake-word script to call."""
    await _event_queue.put("start_voice")
    return {"status": "triggered"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _ensure_thread(client, tid: str):
    """Create the thread if it doesn't already exist."""
    try:
        await client.threads.get(thread_id=tid)
    except Exception:
        await client.threads.create(thread_id=tid)


def _extract_response(result) -> str:
    """Extract all AI text content generated after the last user message."""
    if not isinstance(result, dict):
        logger.warning("Unexpected result type from graph: %s", type(result))
        return ""

    messages = result.get("messages", [])
    if not messages:
        logger.warning("No messages in graph result")
        return ""

    # Find the last human/user message index
    last_user_idx = -1
    for i, msg in enumerate(messages):
        role = msg.get("type", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        if role in ("human", "user"):
            last_user_idx = i

    # Collect AI text content from messages after the last user message
    ai_contents = []
    for msg in messages[last_user_idx + 1:]:
        role = msg.get("type", "") if isinstance(msg, dict) else getattr(msg, "type", "")
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        if role == "ai" and content:
            ai_contents.append(content)

    final_text = "\n\n".join(ai_contents).strip()
    if not final_text:
        logger.warning("No AI response content found after last user message")
    return final_text


# Global exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
