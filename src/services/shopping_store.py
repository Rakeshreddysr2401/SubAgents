"""User-scoped shopping list — a structured list the assistant maintains
("remember we need to buy soap") and the swiggy agent consults when ordering.

Postgres-backed store plus an in-memory fake for hermetic tests, with the same
module-level configure/get pair as reminder_store so tools can reach it.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_COLUMNS = "id, user_id, name, quantity, purchased, created_at, updated_at"


@dataclass
class ShoppingItem:
    id: str
    user_id: str
    name: str
    quantity: str | None
    purchased: bool
    created_at: datetime
    updated_at: datetime


class PostgresShoppingStore:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def add(self, user_id: str, name: str, quantity: str | None = None) -> ShoppingItem:
        item_id = str(uuid.uuid4())
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""INSERT INTO shopping_items (id, user_id, name, quantity)
                        VALUES (%s, %s, %s, %s) RETURNING {_COLUMNS}""",
                    (item_id, user_id, name, quantity),
                )
                return ShoppingItem(**(await cur.fetchone()))

    async def list_for_user(self, user_id: str, include_purchased: bool = True) -> list[ShoppingItem]:
        where = "user_id = %s" + ("" if include_purchased else " AND NOT purchased")
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""SELECT {_COLUMNS} FROM shopping_items WHERE {where}
                        ORDER BY purchased ASC, created_at DESC""",
                    (user_id,),
                )
                return [ShoppingItem(**row) for row in await cur.fetchall()]

    async def find_by_name(self, user_id: str, name: str) -> list[ShoppingItem]:
        """Case-insensitive contains match — tools match by name, not id."""
        async with self._pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""SELECT {_COLUMNS} FROM shopping_items
                        WHERE user_id = %s AND name ILIKE %s
                        ORDER BY created_at DESC""",
                    (user_id, f"%{name}%"),
                )
                return [ShoppingItem(**row) for row in await cur.fetchall()]

    async def set_purchased(self, item_id: str, user_id: str, purchased: bool) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """UPDATE shopping_items SET purchased = %s, updated_at = now()
                   WHERE id = %s AND user_id = %s""",
                (purchased, item_id, user_id),
            )
            return cur.rowcount > 0

    async def remove(self, item_id: str, user_id: str) -> bool:
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM shopping_items WHERE id = %s AND user_id = %s",
                (item_id, user_id),
            )
            return cur.rowcount > 0


class InMemoryShoppingStore:
    """Dict-backed fake for hermetic tests."""

    def __init__(self):
        self._items: dict[str, ShoppingItem] = {}

    async def add(self, user_id: str, name: str, quantity: str | None = None) -> ShoppingItem:
        now = datetime.now(timezone.utc)
        item = ShoppingItem(
            id=str(uuid.uuid4()), user_id=user_id, name=name, quantity=quantity,
            purchased=False, created_at=now, updated_at=now,
        )
        self._items[item.id] = item
        return item

    async def list_for_user(self, user_id: str, include_purchased: bool = True) -> list[ShoppingItem]:
        items = [
            i for i in self._items.values()
            if i.user_id == user_id and (include_purchased or not i.purchased)
        ]
        return sorted(items, key=lambda i: (i.purchased, -i.created_at.timestamp()))

    async def find_by_name(self, user_id: str, name: str) -> list[ShoppingItem]:
        needle = name.lower()
        return [
            i for i in self._items.values()
            if i.user_id == user_id and needle in i.name.lower()
        ]

    async def set_purchased(self, item_id: str, user_id: str, purchased: bool) -> bool:
        item = self._items.get(item_id)
        if item and item.user_id == user_id:
            item.purchased = purchased
            item.updated_at = datetime.now(timezone.utc)
            return True
        return False

    async def remove(self, item_id: str, user_id: str) -> bool:
        item = self._items.get(item_id)
        if item and item.user_id == user_id:
            del self._items[item_id]
            return True
        return False


_store = None


def configure_shopping_store(store) -> None:
    global _store
    _store = store


def get_shopping_store():
    if _store is None:
        raise RuntimeError("Shopping store not configured (lifespan not run?)")
    return _store
