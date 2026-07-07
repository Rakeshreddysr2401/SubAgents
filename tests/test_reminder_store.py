"""Reminder store: user scoping, cancel rules, claim_due idempotency."""

from datetime import datetime, timedelta, timezone

from src.services.reminder_store import InMemoryReminderStore


def _in(minutes: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def test_create_and_list_scoped_by_user():
    store = InMemoryReminderStore()
    await store.create("alice", "stretch", _in(5))
    await store.create("bob", "meeting", _in(10))

    alice = await store.list_for_user("alice")
    assert [r.text for r in alice] == ["stretch"]


async def test_list_orders_pending_soonest_first():
    store = InMemoryReminderStore()
    await store.create("alice", "later", _in(60))
    await store.create("alice", "sooner", _in(5))

    reminders = await store.list_for_user("alice")
    assert [r.text for r in reminders] == ["sooner", "later"]


async def test_cancel_only_pending_and_only_own():
    store = InMemoryReminderStore()
    r = await store.create("alice", "stretch", _in(5))

    assert not await store.cancel(r.id, "bob")  # not the owner
    assert await store.cancel(r.id, "alice")
    assert not await store.cancel(r.id, "alice")  # already cancelled


async def test_claim_due_returns_only_due_and_is_idempotent():
    store = InMemoryReminderStore()
    due = await store.create("alice", "now", _in(-1))
    await store.create("alice", "future", _in(60))

    first = await store.claim_due()
    assert [r.id for r in first] == [due.id]
    assert first[0].status == "fired"
    assert first[0].fired_at is not None

    # A second (overlapping) tick must not re-claim the same reminder.
    assert await store.claim_due() == []


async def test_cancelled_reminder_never_fires():
    store = InMemoryReminderStore()
    r = await store.create("alice", "stretch", _in(-1))
    await store.cancel(r.id, "alice")

    assert await store.claim_due() == []
