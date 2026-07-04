"""FastAPI application factory for the standalone runtime.

Run with:  uv run uvicorn main:app --host 0.0.0.0 --port 2024

The lifespan owns every long-lived resource: the Postgres checkpointer,
Redis and Qdrant clients, Swiggy MCP tools, and the compiled LangGraph graph.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.api import chat, events, frames, uploads
from src.configs.logging_config import get_logger, setup_logging
from src.configs.settings import get_settings
from src.services.redis_client import close_redis, get_redis

logger = get_logger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()

    async with AsyncPostgresSaver.from_conn_string(settings.postgres_dsn) as checkpointer:
        await checkpointer.setup()  # idempotent schema migrations
        logger.info("Postgres checkpointer ready (%s)", settings.postgres_dsn.split("@")[-1])

        app.state.redis = get_redis()  # shared module-level client (tools use it too)

        # Qdrant (shared module-level client so tools can reach it) + collections
        from src.rag.qdrant import ensure_collections, get_qdrant

        app.state.qdrant = get_qdrant()
        try:
            await ensure_collections(app.state.qdrant)
        except Exception as e:
            logger.warning("Qdrant collection setup failed (RAG degraded): %s", e)

        # Mem0 long-term memory (best-effort; graph runs without it)
        app.state.mem0 = None
        try:
            from src.memory.mem0_client import make_mem0

            app.state.mem0 = await make_mem0()
            logger.info("Mem0 memory initialised")
        except Exception as e:
            logger.warning("Mem0 unavailable — long-term memory disabled: %s", e)

        # Load MCP tools asynchronously (no more import-time asyncio.run)
        from src.tools import apply_swiggy_tools
        from src.tools.swiggy_mcp import load_swiggy_tools

        swiggy_tools = await load_swiggy_tools()
        apply_swiggy_tools(swiggy_tools)

        # Build the graph with real persistence (after MCP tools are applied)
        from src.graph.build import build_graph

        app.state.graph = build_graph(checkpointer=checkpointer, mem0=app.state.mem0)
        # Wake-word event fan-out: one queue per connected /events subscriber
        app.state.event_subscribers = set()

        logger.info("SubAgents started — standalone runtime, multimodal mode active")
        try:
            yield
        finally:
            await close_redis()
            await app.state.qdrant.close()
            logger.info("SubAgents stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="SubAgents API", version="0.2.0", lifespan=lifespan)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def chat_ui():
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return index.read_text(encoding="utf-8")
        return "<h1>SubAgents API</h1><p>Chat UI not found. Add static/index.html</p>"

    app.include_router(chat.router)
    app.include_router(frames.router)
    app.include_router(events.router)
    app.include_router(uploads.router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app
