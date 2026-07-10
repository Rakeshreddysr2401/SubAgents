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

from src.api import (
    auth,
    chat,
    events,
    frames,
    guardian,
    music,
    reminders,
    shopping,
    system,
    threads,
    uploads,
)
from src.configs.logging_config import get_logger, setup_logging
from src.configs.settings import get_settings
from src.services.db import ensure_schema, make_pool
from src.services.redis_client import close_redis, get_redis
from src.services.reminder_store import PostgresReminderStore, configure_reminder_store
from src.services.shopping_store import PostgresShoppingStore, configure_shopping_store
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
        app.state.reminder_store = PostgresReminderStore(app.state.db)
        app.state.shopping_store = PostgresShoppingStore(app.state.db)
        # Module-level accessors so the reminder/shopping tools (which can't
        # see app.state) reach the same store instances.
        configure_reminder_store(app.state.reminder_store)
        configure_shopping_store(app.state.shopping_store)

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

        # Load MCP provider tools asynchronously (no import-time network).
        # No token → each provider yields [] with zero network calls.
        from src.services.mcp_providers import load_provider_tools
        from src.tools import apply_mcp_tools

        food_tools = await load_provider_tools("swiggy_food")
        instamart_tools = await load_provider_tools("swiggy_instamart")
        dineout_tools = await load_provider_tools("swiggy_dineout")
        apply_mcp_tools(food_tools, instamart_tools, dineout_tools)
        for provider, tools in (
            ("swiggy_food", food_tools),
            ("swiggy_instamart", instamart_tools),
            ("swiggy_dineout", dineout_tools),
        ):
            for t in tools:
                # One-time enumeration so cart-mutation/order-placement tool
                # names can be identified and added to GATED_TOOL_NAMES
                # (src/commons/constants.py) — not visible in source since
                # these load dynamically from the remote MCP servers.
                logger.info("MCP tool available (%s): %s", provider, t.name)

        # Build the graph with real persistence (after MCP tools are applied)
        from src.graph.build import build_graph

        app.state.graph = build_graph(checkpointer=checkpointer, mem0=app.state.mem0)
        # Server-push events (wake word, reminders, guardian, music) fan out
        # through the module-level broker — per-user routed, JSON payloads.
        from src.services.event_broker import get_broker

        app.state.event_broker = get_broker()

        # Optional in-process wake-word listener (single-command mode)
        wake_stop = _maybe_start_wake_word(app, settings)

        # Background loops: reminder scheduler + guardian camera watcher.
        import asyncio
        from contextlib import suppress

        from src.services.guardian import guardian_loop
        from src.services.reminder_scheduler import reminder_loop

        background_loops = [
            asyncio.create_task(
                reminder_loop(app.state.reminder_store, get_broker(), settings.reminder_poll_seconds)
            ),
            asyncio.create_task(
                guardian_loop(get_broker(), settings.guardian_interval_seconds)
            ),
        ]

        logger.info("SubAgents started — standalone runtime, multimodal mode active")
        try:
            yield
        finally:
            if wake_stop is not None:
                wake_stop.set()
            for task in background_loops:
                task.cancel()
            for task in background_loops:
                with suppress(asyncio.CancelledError):
                    await task
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
        from src.services.event_broker import get_broker
        from src.services.wake_word import run_listener
    except Exception as e:  # pragma: no cover - optional deps
        logger.warning("Wake word enabled but unavailable: %s", e)
        return None

    loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    def _fire():
        n = get_broker().broadcast({"type": "start_voice"})
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
    app = FastAPI(title="SubAgents API", version="0.3.0", lifespan=lifespan)

    settings = get_settings()
    # Same-origin by default (the SPA is served by this process). CORS_ORIGINS
    # opts additional browser origins in, e.g. a LAN hostname running the Vite
    # dev server against this backend.
    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,  # cookie-based sessions
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

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

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page():
        return _serve_spa()

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page():
        return _serve_spa()

    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(frames.router)
    app.include_router(events.router)
    app.include_router(uploads.router)
    app.include_router(threads.router)
    app.include_router(reminders.router)
    app.include_router(shopping.router)
    app.include_router(music.router)
    app.include_router(guardian.router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app
