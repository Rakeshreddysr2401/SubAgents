"""Scheduler tick: due reminders reach only the owner's event queue."""

import json
from datetime import datetime, timedelta, timezone

from src.services.event_broker import EventBroker
from src.services.reminder_scheduler import reminder_tick
from src.services.reminder_store import InMemoryReminderStore


async def test_tick_routes_reminder_only_to_owner():
    store = InMemoryReminderStore()
    broker = EventBroker()
    q_alice = broker.subscribe("alice")
    q_bob = broker.subscribe("bob")
    reminder = await store.create("alice", "stretch", datetime.now(timezone.utc) - timedelta(seconds=1))

    fired = await reminder_tick(store, broker)

    assert fired == 1
    event = json.loads(q_alice.get_nowait())
    assert event["type"] == "reminder"
    assert event["reminder"]["id"] == reminder.id
    assert event["reminder"]["text"] == "stretch"
    assert q_bob.empty()


async def test_tick_with_nothing_due_is_noop():
    store = InMemoryReminderStore()
    broker = EventBroker()
    q = broker.subscribe("alice")
    await store.create("alice", "future", datetime.now(timezone.utc) + timedelta(hours=1))

    assert await reminder_tick(store, broker) == 0
    assert q.empty()


async def test_reminder_fires_even_with_no_subscriber():
    """No browser connected: the reminder is still claimed (marked fired) so
    it shows in the panel's past section later, rather than refiring forever."""
    store = InMemoryReminderStore()
    broker = EventBroker()
    await store.create("alice", "stretch", datetime.now(timezone.utc) - timedelta(seconds=1))

    assert await reminder_tick(store, broker) == 1
    assert await reminder_tick(store, broker) == 0
