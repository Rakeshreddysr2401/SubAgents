"""User-scoped scheduled reminders, fired by src/services/reminder_scheduler.py.

Postgres-backed store plus an in-memory fake for hermetic tests. A module-level
configure/get pair (like get_redis()) lets LangChain tools reach the store
without access to app.state.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

PENDING = "pending"
FIRED = "fired"
CANCELLED = "cancelled"


@dataclass
class Reminder:
    id: str
    user_id: str
    text: str
    due_at: datetime
    status: str
    created_at: datetime
    fired_at: datetime | None


class PostgresReminderStore:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def create(self, user_id: str, text: str, due_at: datetime) -> Reminder:
        reminder_id = str(uuid.uuid4())
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """INSERT INTO reminders (id, user_id, text, due_at)
                       VALUES (%s, %s, %s, %s)
                       RETURNING id, user_id, text, due_at, status, created_at, fired_at""",
                    (reminder_id, user_id, text, due_at),
                )
                row = await cur.fetchone()
                return Reminder(**row)

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Reminder]:
        """Pending first (soonest due first), then recently fired/cancelled."""
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """SELECT id, user_id, text, due_at, status, created_at, fired_at
                       FROM reminders WHERE user_id = %s
                       ORDER BY (status = 'pending') DESC,
                                CASE WHEN status = 'pending' THEN due_at END ASC,
                                due_at DESC
                       LIMIT %s""",
                    (user_id, limit),
                )
                rows = await cur.fetchall()
                return [Reminder(**row) for row in rows]

    async def cancel(self, reminder_id: str, user_id: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """UPDATE reminders SET status = 'cancelled'
                   WHERE id = %s AND user_id = %s AND status = 'pending'""",
                (reminder_id, user_id),
            )
            return cur.rowcount > 0

    async def claim_due(self, now: datetime | None = None) -> list[Reminder]:
        """Atomically mark all due pending reminders fired and return them.

        UPDATE ... RETURNING makes firing idempotent: overlapping ticks can't
        double-claim the same reminder.
        """
        now = now or datetime.now(timezone.utc)
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """UPDATE reminders SET status = 'fired', fired_at = now()
                       WHERE status = 'pending' AND due_at <= %s
                       RETURNING id, user_id, text, due_at, status, created_at, fired_at""",
                    (now,),
                )
                rows = await cur.fetchall()
                return [Reminder(**row) for row in rows]


class InMemoryReminderStore:
    """Dict-backed fake for hermetic tests."""

    def __init__(self):
        self._reminders: dict[str, Reminder] = {}

    async def create(self, user_id: str, text: str, due_at: datetime) -> Reminder:
        reminder = Reminder(
            id=str(uuid.uuid4()),
            user_id=user_id,
            text=text,
            due_at=due_at,
            status=PENDING,
            created_at=datetime.now(timezone.utc),
            fired_at=None,
        )
        self._reminders[reminder.id] = reminder
        return reminder

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Reminder]:
        mine = [r for r in self._reminders.values() if r.user_id == user_id]
        pending = sorted((r for r in mine if r.status == PENDING), key=lambda r: r.due_at)
        rest = sorted((r for r in mine if r.status != PENDING), key=lambda r: r.due_at, reverse=True)
        return (pending + rest)[:limit]

    async def cancel(self, reminder_id: str, user_id: str) -> bool:
        r = self._reminders.get(reminder_id)
        if r and r.user_id == user_id and r.status == PENDING:
            r.status = CANCELLED
            return True
        return False

    async def claim_due(self, now: datetime | None = None) -> list[Reminder]:
        now = now or datetime.now(timezone.utc)
        due = [r for r in self._reminders.values() if r.status == PENDING and r.due_at <= now]
        for r in due:
            r.status = FIRED
            r.fired_at = datetime.now(timezone.utc)
        return due


_store = None


def configure_reminder_store(store) -> None:
    global _store
    _store = store


def get_reminder_store():
    if _store is None:
        raise RuntimeError("Reminder store not configured (lifespan not run?)")
    return _store
