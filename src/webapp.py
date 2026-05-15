"""
Custom FastAPI webapp integrated with LangGraph Server.
Mounted into the LangGraph runtime via langgraph.json -> http.app.

Routes:
  GET  /         -> Chat UI (static/index.html)
  POST /chat     -> Send message, get response (same contract as main.py)
  GET  /health   -> Health check
  GET  /history/{thread_id} -> Conversation history
"""
from uuid import uuid4

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
import asyncio

logger = get_logger(__name__)

# Queue for sending events to the UI
_event_queue = asyncio.Queue()

# In-memory conversation history keyed by thread_id
_conversations: dict[str, list[dict]] = {}

# Lazy-initialised SDK client (reuses connection pool)
_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hook."""
    logger.info("OWP Agent started — Multimodal mode active")
    yield
    logger.info("OWP Agent stopped")


def _get_client():
    """Get LangGraph SDK client pointing to the local LangGraph Server."""
    global _client
    if _client is None:
        _client = get_client(url="http://127.0.0.1:2024")
    return _client


app = FastAPI(title="OWP Agent Custom API", version="0.1.0", lifespan=lifespan)

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
    return "<h1>OWP Agent API</h1><p>Chat UI not found. Add static/index.html</p>"


@app.post("/chat")
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    thread_id: str = Query(default=None),
):
    """
    Send a message and stream the response.
    Uses LangGraph SDK to stream chunks of the AI response.
    """
    tid = thread_id or str(uuid4())
    client = _get_client()

    # Ensure conversation history exists
    if tid not in _conversations:
        _conversations[tid] = []

    _conversations[tid].append({"role": "user", "content": request.query})
    logger.info("Chat request: thread=%s, query=%s", tid, request.query[:80])

    async def event_generator():
        try:
            # Ensure thread exists in LangGraph Server
            await _ensure_thread(client, tid)

            # Fallback to wait() for reliability while we debug streaming
            result = await client.runs.wait(
                thread_id=tid,
                assistant_id="agent",
                input={
                    "messages": [{"role": "user", "content": request.query}],
                    "always_speak": request.always_speak
                }
            )
            
            # Extract response from the final state
            full_response = _extract_response(result)

            if full_response:
                _conversations[tid].append({"role": "assistant", "content": full_response})
                # Yield the content as a single chunk for the frontend stream reader
                yield f"data: {full_response}\n\n"
                
                if request.always_speak:
                    # Speak in background to not block the connection close
                    background_tasks.add_task(speak_out_loud, full_response)
            
            # Send metadata to signal end
            yield f"data: [DONE] {tid}\n\n"

        except Exception as e:
            logger.error(f"Streaming chat failed: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"

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
                # Binary path (Fastest - for Jetson)
                import base64
                data = base64.b64encode(message["bytes"]).decode("utf-8")
                store_frame(tid, data)
            elif "text" in message:
                # Text path (Compatibility - for Browser)
                store_frame(tid, message["text"])
    except WebSocketDisconnect:
        logger.info("Video WebSocket disconnected: thread=%s", tid)
    except Exception as e:
        logger.warning("Video WebSocket error: thread=%s, err=%s", tid, e)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "owp-agent"}


@app.get("/history/{thread_id}")
async def get_history(thread_id: str):
    """Get conversation history for a thread."""
    if thread_id not in _conversations:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"thread_id": thread_id, "messages": _conversations[thread_id]}


@app.get("/events")
async def events(request: Request):
    """Event stream for waking up the browser UI."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                # Wait for a trigger
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
    """Extract the last AI message with content."""
    if not result:
        logger.warning("No result from graph invocation")
        return ""

    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in reversed(messages):
        # Check if it's an AI message with content
        role = ""
        content = ""
        
        if isinstance(msg, dict):
            role = msg.get("type", "")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "type", "")
            content = getattr(msg, "content", "")

        if role == "ai" and content:
            # We found the response text
            return content

    logger.warning("No AI response content found in result")
    return ""


# Global exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
