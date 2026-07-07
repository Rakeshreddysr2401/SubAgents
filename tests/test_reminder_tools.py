"""Reminder tools: datetime validation, user scoping, update events."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.services.event_broker import get_broker, reset_broker
from src.services.reminder_store import InMemoryReminderStore, configure_reminder_store
from src.tools.reminder_tools import cancel_reminder, create_reminder, list_reminders


@pytest.fixture(autouse=True)
def fresh_state():
    reset_broker()
    store = InMemoryReminderStore()
    configure_reminder_store(store)
    yield store
    configure_reminder_store(None)
    reset_broker()


def _config(user_id: str = "u1") -> dict:
    return {"configurable": {"user_id": user_id, "thread_id": "t1"}}


async def test_create_reminder_happy_path(fresh_state):
    q = get_broker().subscribe("u1")
    due = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    result = await create_reminder.ainvoke({"text": "stretch", "due_at": due}, config=_config())

    assert "Reminder set" in result
    reminders = await fresh_state.list_for_user("u1")
    assert len(reminders) == 1 and reminders[0].text == "stretch"
    assert json.loads(q.get_nowait()) == {"type": "reminders_updated"}


async def test_create_reminder_rejects_bad_datetime(fresh_state):
    result = await create_reminder.ainvoke({"text": "x", "due_at": "five o'clock"}, config=_config())
    assert "Could not parse" in result
    assert await fresh_state.list_for_user("u1") == []


async def test_create_reminder_rejects_past_datetime(fresh_state):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    result = await create_reminder.ainvoke({"text": "x", "due_at": past}, config=_config())
    assert "in the past" in result
    assert await fresh_state.list_for_user("u1") == []


async def test_list_and_cancel_round_trip(fresh_state):
    due = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    await create_reminder.ainvoke({"text": "stretch", "due_at": due}, config=_config())
    reminder_id = (await fresh_state.list_for_user("u1"))[0].id

    listing = await list_reminders.ainvoke({}, config=_config())
    assert "stretch" in listing and reminder_id in listing

    result = await cancel_reminder.ainvoke({"reminder_id": reminder_id}, config=_config())
    assert "cancelled" in result.lower()


async def test_cancel_other_users_reminder_fails(fresh_state):
    due = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    await create_reminder.ainvoke({"text": "stretch", "due_at": due}, config=_config("u1"))
    reminder_id = (await fresh_state.list_for_user("u1"))[0].id

    result = await cancel_reminder.ainvoke({"reminder_id": reminder_id}, config=_config("u2"))
    assert "No pending reminder" in result
