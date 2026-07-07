"""Shared async Postgres pool for relational app data (users, chat threads).

Separate from the LangGraph checkpointer's own connection — this pool backs
plain relational tables that have nothing to do with graph state.
"""

from psycopg_pool import AsyncConnectionPool

from src.configs.settings import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chat_threads_user_id_updated_at_idx
    ON chat_threads (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | fired | cancelled
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fired_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS reminders_status_due_idx ON reminders (status, due_at);
CREATE INDEX IF NOT EXISTS reminders_user_due_idx ON reminders (user_id, due_at DESC);

CREATE TABLE IF NOT EXISTS shopping_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity TEXT,
    purchased BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS shopping_items_user_idx
    ON shopping_items (user_id, purchased, created_at DESC);
"""


async def make_pool() -> AsyncConnectionPool:
    pool = AsyncConnectionPool(get_settings().postgres_dsn, open=False)
    await pool.open()
    return pool


async def ensure_schema(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(_SCHEMA)
    if get_settings().auth_disabled:
        # AUTH_DISABLED routes every request to user_id "default_user"
        # (src.api.auth.DEFAULT_USER) without ever going through /auth/signup,
        # so chat_threads' FK on users(id) would otherwise reject the very
        # first /chat call in this mode.
        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO users (id, email, password_hash)
                   VALUES ('default_user', 'dev@localhost', '')
                   ON CONFLICT (id) DO NOTHING"""
            )
