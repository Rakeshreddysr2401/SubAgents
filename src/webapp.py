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
    from src.tools.swiggy_mcp import close_swiggy_session
    await close_swiggy_session()
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
    index_path = _STATIC_DIR / "index.html"
    if _STATIC_DIR.exists() and index_path.exists():
        content = await asyncio.to_thread(index_path.read_text, encoding="utf-8")
        return content
    return "<h1>OWP Agent API</h1><p>Chat UI not found. Add static/index.html</p>"


@app.post("/chat")
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    thread_id: str = Query(default=None),
):
    """
    Send a message and stream the response.
    Uses LangGraph SDK to stream events from the graph.
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

            full_response = ""
            processed_msg_ids = set()
            logger.info("Starting stream for thread=%s", tid)
            
            # Use stream() with values mode
            async for event in client.runs.stream(
                thread_id=tid,
                assistant_id="agent",
                input={
                    "messages": [{"role": "user", "content": request.query}],
                    "always_speak": request.always_speak
                },
                stream_mode="values",
            ):
                if event.event == "values":
                    data = event.data
                    if "messages" in data and len(data["messages"]) > 0:
                        last_msg = data["messages"][-1]
                        
                        msg_id = None
                        if isinstance(last_msg, dict):
                            msg_id = last_msg.get("id")
                            role = last_msg.get("type") or last_msg.get("role")
                            content = last_msg.get("content", "")
                        else:
                            msg_id = getattr(last_msg, "id", None)
                            role = getattr(last_msg, "type", "") or getattr(last_msg, "role", "")
                            content = getattr(last_msg, "content", "")

                        # Skip if we already processed this specific message
                        if msg_id and msg_id in processed_msg_ids:
                            continue
                        
                        if (role in ["ai", "assistant", "tool"]) and content:
                            if msg_id:
                                processed_msg_ids.add(msg_id)
                            
                            if isinstance(content, list):
                                text_blocks = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                                content = "".join(text_blocks)
                            
                            if content and isinstance(content, str):
                                # If it's an AI message, we track it for history/speech
                                if role in ["ai", "assistant"]:
                                    full_response = content
                                
                                for line in content.split("\n"):
                                    yield f"data: {line}\n"
                                yield "\n"

            if full_response:
                _conversations[tid].append({"role": "assistant", "content": full_response})
                if request.always_speak:
                    try:
                        from src.tools.audio_tools import speak_out_loud
                        # speak_out_loud is a tool object, use its .func to call it directly
                        background_tasks.add_task(speak_out_loud.func, full_response)
                    except Exception as audio_err:
                        logger.warning("Failed to queue background speech: %s", audio_err)
            else:
                logger.warning("Stream ended with no AI content for thread=%s", tid)
            
            # Send metadata to signal end
            yield f"data: [DONE] {tid}\n\n"

        except Exception as e:
            logger.error("Streaming chat failed for thread=%s: %s", tid, e, exc_info=True)
            # Ensure the error is also properly formatted as SSE
            error_msg = str(e)
            for line in error_msg.split("\n"):
                yield f"data: [ERROR] {line}\n"
            yield "\n"

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


# Global exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
