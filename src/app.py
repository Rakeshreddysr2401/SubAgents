"""FastAPI application factory for the standalone runtime.

Run with:  uv run uvicorn main:app --host 0.0.0.0 --port 2024

The lifespan owns every long-lived resource: the Postgres checkpointer,
Redis and Qdrant clients, Swiggy MCP tools, and the compiled LangGraph graph.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.api import auth, chat, events, frames, threads, uploads
from src.configs.logging_config import get_logger, setup_logging
from src.configs.settings import get_settings
from src.services.db import ensure_schema, make_pool
from src.services.redis_client import close_redis, get_redis
from src.services.thread_store import PostgresThreadStore
from src.services.user_store import PostgresUserStore

logger = get_logger(__name__)

_WEB_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()

    async with AsyncPostgresSaver.from_conn_string(settings.postgres_dsn) as checkpointer:
        await checkpointer.setup()  # idempotent schema migrations
        logger.info("Postgres checkpointer ready (%s)", settings.postgres_dsn.split("@")[-1])

        app.state.redis = get_redis()  # shared module-level client (tools use it too)

        # Relational app data: users + chat_threads (separate pool from the checkpointer)
        app.state.db = await make_pool()
        await ensure_schema(app.state.db)
        app.state.user_store = PostgresUserStore(app.state.db)
        app.state.thread_store = PostgresThreadStore(app.state.db)

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
        for t in swiggy_tools:
            # One-time enumeration so cart-mutation/order-placement tool names
            # can be identified and added to GATED_TOOL_NAMES (src/commons/
            # constants.py) — not visible in source since these load
            # dynamically from the remote Swiggy MCP server.
            logger.info("Swiggy MCP tool available: %s", t.name)

        # Build the graph with real persistence (after MCP tools are applied)
        from src.graph.build import build_graph

        app.state.graph = build_graph(checkpointer=checkpointer, mem0=app.state.mem0)
        # Wake-word event fan-out: one queue per connected /events subscriber
        app.state.event_subscribers = set()

        # Optional in-process wake-word listener (single-command mode)
        wake_stop = _maybe_start_wake_word(app, settings)

        logger.info("SubAgents started — standalone runtime, multimodal mode active")
        try:
            yield
        finally:
            if wake_stop is not None:
                wake_stop.set()
            await close_redis()
            await app.state.qdrant.close()
            await app.state.db.close()
            logger.info("SubAgents stopped")


def _maybe_start_wake_word(app: FastAPI, settings):
    """Start the wake-word detector in a background thread if enabled.

    Returns the threading.Event used to stop it, or None if disabled/unavailable.
    On detection the audio thread hands the event back to the loop via
    call_soon_threadsafe, then fans it out to /events subscribers.
    """
    if not settings.wake_word_enabled:
        return None

    import asyncio
    import threading

    try:
        from src.api.events import broadcast_event
        from src.services.wake_word import run_listener
    except Exception as e:  # pragma: no cover - optional deps
        logger.warning("Wake word enabled but unavailable: %s", e)
        return None

    loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    def _fire():
        n = broadcast_event(app, "start_voice")
        logger.info(">>> Wake word detected — notified %d browser subscriber(s)", n)

    def on_detect():
        loop.call_soon_threadsafe(_fire)

    def target():
        try:
            run_listener(settings, on_detect, stop_event)
        except Exception as e:
            logger.warning("Wake-word listener stopped: %s", e)

    threading.Thread(target=target, name="wake-word", daemon=True).start()
    logger.info("In-process wake-word listener enabled (engine=%s, word=%s)",
                settings.wake_word_engine, settings.wake_word)
    return stop_event


def create_app() -> FastAPI:
    app = FastAPI(title="SubAgents API", version="0.2.0", lifespan=lifespan)

    # React SPA (web/), built via `npm run build` in web/ -> web/dist/. Vite's
    # index.html references /assets/*.js|css and /favicon.svg directly, so
    # those are mounted at the paths it expects; the SPA shell itself is
    # served for the three top-level page routes (explicit routes, not a
    # catch-all, so nothing here can shadow an API router below).
    if _WEB_DIST_DIR.exists():
        app.mount("/assets", StaticFiles(directory=_WEB_DIST_DIR / "assets"), name="web-assets")

    def _serve_spa() -> str:
        index_html = _WEB_DIST_DIR / "index.html"
        if index_html.exists():
            return index_html.read_text(encoding="utf-8")
        return "<h1>SubAgents API</h1><p>Web app not built. Run `npm run build` in web/.</p>"

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        favicon_path = _WEB_DIST_DIR / "favicon.svg"
        if favicon_path.exists():
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404)

    @app.get("/", response_class=HTMLResponse)
    async def chat_ui():
        return _serve_spa()

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        return _serve_spa()

    @app.get("/account", response_class=HTMLResponse)
    async def account_page():
        return _serve_spa()

    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(frames.router)
    app.include_router(events.router)
    app.include_router(uploads.router)
    app.include_router(threads.router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app
