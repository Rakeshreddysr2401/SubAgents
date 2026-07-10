"""Per-user server-push event broker backing the /events SSE channel.

Module-level singleton (like get_redis()) so tools, the reminder scheduler and
the guardian loop can push events without access to app.state. All payloads are
dicts serialized to one JSON string per broadcast; the client dispatches on the
"type" key and ignores unknown types, so new event types are additive.

Must be used from the app's event loop — from other threads, hand off with
loop.call_soon_threadsafe (see src/app.py's wake-word listener).
"""

import asyncio
import json
from dataclasses import dataclass


@dataclass
class _Subscriber:
    queue: asyncio.Queue
    user_id: str


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: list[_Subscriber] = []

    def subscribe(self, user_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(_Subscriber(queue=queue, user_id=user_id))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers = [s for s in self._subscribers if s.queue is not queue]

    def subscriber_count(self, user_id: str | None = None) -> int:
        """Active subscriptions for one user (or everyone with None)."""
        if user_id is None:
            return len(self._subscribers)
        return sum(1 for s in self._subscribers if s.user_id == user_id)

    def broadcast(self, payload: dict, user_id: str | None = None) -> int:
        """Push a JSON event to every subscriber of `user_id` (None = everyone).

        Returns the number of queues the event reached.
        """
        data = json.dumps(payload)
        count = 0
        for sub in list(self._subscribers):
            if user_id is None or sub.user_id == user_id:
                sub.queue.put_nowait(data)
                count += 1
        return count


_broker: EventBroker | None = None


def get_broker() -> EventBroker:
    global _broker
    if _broker is None:
        _broker = EventBroker()
    return _broker


def reset_broker() -> None:
    """Test seam: drop the singleton so each test gets a fresh broker."""
    global _broker
    _broker = None
