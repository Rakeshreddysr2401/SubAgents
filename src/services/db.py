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
"""


async def make_pool() -> AsyncConnectionPool:
    pool = AsyncConnectionPool(get_settings().postgres_dsn, open=False)
    await pool.open()
    return pool


async def ensure_schema(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(_SCHEMA)
