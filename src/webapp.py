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

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from langgraph_sdk import get_client

from src.configs.logging_config import get_logger
from src.models.schema import ChatRequest, ChatResponse
from src.utils.frame_buffer import store_frame
from src.utils.perception_loop import get_perception_loop

# Offload blocking perception work off the async event loop
_frame_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="frame")

logger = get_logger(__name__)

# In-memory conversation history keyed by thread_id
_conversations: dict[str, list[dict]] = {}

# Lazy-initialised SDK client (reuses connection pool)
_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hook."""
    logger.info("OWP Agent started — 5-minute rolling memory active")
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


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    thread_id: str = Query(default=None, description="Thread ID for conversation continuity"),
):
    """
    Send a message and get a response.
    Uses LangGraph SDK to invoke the graph through the LangGraph runtime.
    """
    tid = thread_id or str(uuid4())
    client = _get_client()

    # Ensure conversation history exists
    if tid not in _conversations:
        _conversations[tid] = []

    _conversations[tid].append({"role": "user", "content": request.query})
    logger.info("Chat request: thread=%s, query=%s", tid, request.query[:80])

    try:
        # Ensure thread exists in LangGraph Server
        await _ensure_thread(client, tid)

        result = await client.runs.wait(
            thread_id=tid,
            assistant_id="agent",
            input={"messages":[{"role": "user", "content": request.query}]},
        )


        response_text = _extract_response(result)

        if response_text:
            _conversations[tid].append({"role": "assistant", "content": response_text})

        return ChatResponse(
            response=response_text,
            thread_id=tid,
            messages=_conversations[tid],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat request failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Chat request failed: {str(e)}")


@app.websocket("/ws/frames")
async def video_frame_ws(ws: WebSocket, thread_id: str = Query(default=None)):
    """Receive video frames from the browser over WebSocket.

    The client sends base64-encoded JPEG strings every ~2 seconds.
    Frames are stored in a rolling buffer keyed by thread_id.
    """
    await ws.accept()
    tid = thread_id or "default"
    logger.info("Video WebSocket connected: thread=%s", tid)

    perception = get_perception_loop()

    loop = asyncio.get_event_loop()

    def _process_frame(data: str):
        store_frame(tid, data)
        perception.on_frame(tid, data)

    try:
        while True:
            data = await ws.receive_text()
            # Offload to thread — keeps the async event loop free for other requests
            loop.run_in_executor(_frame_executor, _process_frame, data)
    except WebSocketDisconnect:

        logger.info("Video WebSocket disconnected: thread=%s", tid)
        perception.reset_thread(tid)
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
    """Extract the last AI message with content and no tool_calls."""
    if not result:
        logger.warning("No result from graph invocation")
        return ""

    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in reversed(messages):
        if isinstance(msg, dict):
            if msg.get("type") == "ai" and msg.get("content") and not msg.get("tool_calls"):
                return msg["content"]
        else:
            if getattr(msg, "type", None) == "ai" and getattr(msg, "content", None) and not getattr(msg, "tool_calls", None):
                return msg.content

    logger.warning("No AI response found in result")
    return ""


# Global exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
