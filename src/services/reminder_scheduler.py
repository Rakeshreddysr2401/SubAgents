"""Fires due reminders to the owner's browser via the event broker.

A lifespan-owned asyncio loop (no scheduler library needed at this scale):
every tick atomically claims due reminders (UPDATE ... RETURNING in the store,
so overlapping ticks can't double-fire) and pushes one `{"type": "reminder"}`
event per reminder, routed only to the owning user. A reminder that fires
while no browser is connected is still marked fired — it shows up in the
Reminders panel's past section on next load.
"""

import asyncio
from datetime import datetime, timezone

from src.configs.logging_config import get_logger

logger = get_logger(__name__)


async def reminder_tick(store, broker, now: datetime | None = None) -> int:
    """Claim + broadcast everything due. Returns how many reminders fired."""
    due = await store.claim_due(now or datetime.now(timezone.utc))
    for reminder in due:
        delivered = broker.broadcast(
            {
                "type": "reminder",
                "reminder": {
                    "id": reminder.id,
                    "text": reminder.text,
                    "due_at": reminder.due_at.isoformat(),
                },
            },
            user_id=reminder.user_id,
        )
        logger.info(
            "Reminder %s fired for user=%s (delivered to %d subscriber(s))",
            reminder.id, reminder.user_id, delivered,
        )
    return len(due)


async def reminder_loop(store, broker, interval_seconds: float) -> None:
    """Run reminder_tick forever; one bad tick never kills the loop."""
    while True:
        try:
            await reminder_tick(store, broker)
        except Exception as e:
            logger.warning("Reminder tick failed: %s", e)
        await asyncio.sleep(interval_seconds)
