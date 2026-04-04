#main.py
"""

OWP Agent - Production FastAPI Server

This is the production client-facing API server.
Runs separately from LangGraph Studio (which is for development only).

Architecture:
- FastAPI server for client API (this file) - Port 8000
- LangGraph Studio for development UI - Port 2024 (langgraph dev)

Run: python main.py
"""
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

from src.configs.logging_config import setup_logging, get_logger
setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)

from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage

from src.models.schema import ChatRequest,ChatResponse
from graph import graph
from src.configs.memory_config import get_memory
from src.configs.request_context import bearer_token_var
from src.auth.jwt_auth import authenticate, CurrentUser
from src.auth.token_service import create_token
from src.utils.frame_buffer import store_frame, get_latest_frames

# Standalone mode: uses PostgresSaver when POSTGRES_URI is set, else MemorySaver
# (LangGraph Server provides its own checkpointer, but main.py runs independently)


# In-memory conversation history keyed by thread_id.
# Each value is a list of {"role": "user"|"assistant", "content": "..."}
_conversations: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("Lang Robo Starting up...")
    yield
    logger.info("Lang Robo Shutting down...")


app = FastAPI(title="Lang Robo Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Chat UI (serve static/index.html at root)
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent / "static"


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Serve the built-in chat UI."""
    return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------

async def verify_auth(
    authorization: str = Header(None, description="Bearer token (optional in dev)"),
) -> CurrentUser:
    """
    Validate the Authorization header using JWT.
    Falls back to DEV_API_KEY in development mode.
    """
    # If no authorization header, try DEV_TOKEN
    if not authorization:
        dev_token = os.getenv("DEV_TOKEN")
        if dev_token:
            logger.debug("Using DEV_TOKEN for authentication")
            user = authenticate(dev_token)
            if user:
                return user
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header and no DEV_API_KEY"
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must start with 'Bearer '"
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token is empty")

    user = authenticate(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_response(result: dict) -> str:
    """Return the last AI message with content and no tool_calls."""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            return msg.content
    return ""


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    thread_id: str = Query(default=None, description="Thread ID for conversation continuity"),
    user: CurrentUser = Depends(verify_auth),
):
    """Send a message and get a response."""
    tid = thread_id or str(uuid4())
    config = {
        "configurable": {
            "thread_id": tid,
            "langgraph_auth_user": {
                "identity": user.client_id,
                "client_id": user.client_id,
                "token": user.token,
            },
        }
    }

    # Ensure conversation list exists for this thread
    if tid not in _conversations:
        _conversations[tid] = []

    # Record the user's message
    _conversations[tid].append({"role": "user", "content": request.query})
    logger.info("Chat request: thread=%s, user=%s, query=%s", tid, user.client_id, request.query[:80])

    # Make the caller's Bearer token available to downstream API calls (e.g. claims API)
    bearer_token_var.set(user.token)

    # Build graph input — include video frames if the camera is streaming
    graph_input: dict = {"messages": [{"role": "user", "content": request.query}]}
    frames = get_latest_frames(tid, count=1)
    if frames:
        graph_input["video_frames"] = frames
        logger.info("Including %d video frame(s) in graph input", len(frames))

    result = await graph.ainvoke(graph_input, config=config)

    response_text = extract_response(result)

    # Record the assistant's response
    if response_text:
        _conversations[tid].append({"role": "assistant", "content": response_text})

    return ChatResponse(
        response=response_text,
        thread_id=tid,
        messages=_conversations[tid],
    )


@app.post("/login")
def login():
    # TODO: Replace with DB later
    user = {
        "id": "123",
        "email": "test@email.com"
    }

    token = create_token(user["id"], user["email"])

    return {"access_token": token}

@app.websocket("/ws/frames")
async def video_frame_ws(ws: WebSocket, thread_id: str = Query(default=None)):
    """Receive base64-encoded JPEG frames from the browser."""
    await ws.accept()
    tid = thread_id or "default"
    logger.info("Video WebSocket connected: thread=%s", tid)
    try:
        while True:
            data = await ws.receive_text()
            store_frame(tid, data)
    except WebSocketDisconnect:
        logger.info("Video WebSocket disconnected: thread=%s", tid)
    except Exception as e:
        logger.warning("Video WebSocket error: thread=%s, err=%s", tid, e)








# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
