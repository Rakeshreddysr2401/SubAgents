"""User persistence: a Postgres-backed store plus an in-memory fake for tests.

Both implementations share the same async method surface (create, get_by_email,
get_by_id, update_password, delete) so `src/api/auth.py` and tests can swap
one for the other via `app.state.user_store`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    created_at: datetime


class EmailAlreadyExists(Exception):
    pass


class PostgresUserStore:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def create(self, email: str, password_hash: str) -> User:
        user_id = str(uuid.uuid4())
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                try:
                    await cur.execute(
                        """INSERT INTO users (id, email, password_hash)
                           VALUES (%s, %s, %s)
                           RETURNING id, email, password_hash, created_at""",
                        (user_id, email.lower(), password_hash),
                    )
                except Exception as e:
                    if "unique" in str(e).lower():
                        raise EmailAlreadyExists(email) from e
                    raise
                row = await cur.fetchone()
                return User(**row)

    async def get_by_email(self, email: str) -> User | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, email, password_hash, created_at FROM users WHERE email = %s",
                    (email.lower(),),
                )
                row = await cur.fetchone()
                return User(**row) if row else None

    async def get_by_id(self, user_id: str) -> User | None:
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT id, email, password_hash, created_at FROM users WHERE id = %s",
                    (user_id,),
                )
                row = await cur.fetchone()
                return User(**row) if row else None

    async def update_password(self, user_id: str, password_hash: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                "UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id)
            )

    async def delete(self, user_id: str) -> None:
        async with self._pool.connection() as conn:
            await conn.execute("DELETE FROM users WHERE id = %s", (user_id,))


class InMemoryUserStore:
    """Dict-backed fake for hermetic tests."""

    def __init__(self):
        self._by_id: dict[str, User] = {}

    async def create(self, email: str, password_hash: str) -> User:
        email = email.lower()
        if any(u.email == email for u in self._by_id.values()):
            raise EmailAlreadyExists(email)
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc),
        )
        self._by_id[user.id] = user
        return user

    async def get_by_email(self, email: str) -> User | None:
        email = email.lower()
        return next((u for u in self._by_id.values() if u.email == email), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    async def update_password(self, user_id: str, password_hash: str) -> None:
        if user_id in self._by_id:
            self._by_id[user_id].password_hash = password_hash

    async def delete(self, user_id: str) -> None:
        self._by_id.pop(user_id, None)
