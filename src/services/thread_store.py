"""Chat-thread metadata (title, ownership, last-active) for the sidebar.

The actual message history lives in the LangGraph checkpointer, keyed by
thread_id; this store only tracks *whose* thread it is and what to call it.
Postgres-backed store plus an in-memory fake for hermetic tests.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_TITLE_MAX_LEN = 60


@dataclass
class Thread:
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime


def _derive_title(first_message: str) -> str:
    text = " ".join(first_message.split())
    if len(text) <= _TITLE_MAX_LEN:
        return text or "New chat"
    return text[:_TITLE_MAX_LEN].rstrip() + "…"


class PostgresThreadStore:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def touch(self, thread_id: str, user_id: str, first_message: str) -> None:
        title = _derive_title(first_message)
        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO chat_threads (id, user_id, title)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE
                   SET updated_at = now()
                   WHERE chat_threads.user_id = EXCLUDED.user_id""",
                (thread_id, user_id, title),
            )

    async def list_for_user(self, user_id: str) -> list[Thread]:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at
                       FROM chat_threads WHERE user_id = %s
                       ORDER BY updated_at DESC""",
                    (user_id,),
                )
                rows = await cur.fetchall()
                return [Thread(**row) for row in rows]

    async def get(self, thread_id: str) -> Thread | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at
                       FROM chat_threads WHERE id = %s""",
                    (thread_id,),
                )
                row = await cur.fetchone()
                return Thread(**row) if row else None

    async def delete(self, thread_id: str, user_id: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM chat_threads WHERE id = %s AND user_id = %s", (thread_id, user_id)
            )
            return cur.rowcount > 0

    async def rename(self, thread_id: str, user_id: str, title: str) -> bool:
        title = title.strip()[:_TITLE_MAX_LEN] or "New chat"
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE chat_threads SET title = %s WHERE id = %s AND user_id = %s",
                (title, thread_id, user_id),
            )
            return cur.rowcount > 0


class InMemoryThreadStore:
    """Dict-backed fake for hermetic tests."""

    def __init__(self):
        self._threads: dict[str, Thread] = {}

    async def touch(self, thread_id: str, user_id: str, first_message: str) -> None:
        existing = self._threads.get(thread_id)
        now = datetime.now(timezone.utc)
        if existing is None:
            self._threads[thread_id] = Thread(
                id=thread_id,
                user_id=user_id,
                title=_derive_title(first_message),
                created_at=now,
                updated_at=now,
            )
        elif existing.user_id == user_id:
            existing.updated_at = now

    async def list_for_user(self, user_id: str) -> list[Thread]:
        threads = [t for t in self._threads.values() if t.user_id == user_id]
        return sorted(threads, key=lambda t: t.updated_at, reverse=True)

    async def get(self, thread_id: str) -> Thread | None:
        return self._threads.get(thread_id)

    async def delete(self, thread_id: str, user_id: str) -> bool:
        t = self._threads.get(thread_id)
        if t and t.user_id == user_id:
            del self._threads[thread_id]
            return True
        return False

    async def rename(self, thread_id: str, user_id: str, title: str) -> bool:
        t = self._threads.get(thread_id)
        if t and t.user_id == user_id:
            t.title = title.strip()[:_TITLE_MAX_LEN] or "New chat"
            return True
        return False
