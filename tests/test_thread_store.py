"""InMemoryThreadStore: chat-thread ownership/title/ordering for the sidebar."""

import pytest

from src.services.thread_store import InMemoryThreadStore


@pytest.fixture
def store():
    return InMemoryThreadStore()


async def test_touch_creates_thread_with_derived_title(store):
    await store.touch("t1", "user-1", "What's the weather like today?")
    thread = await store.get("t1")
    assert thread.user_id == "user-1"
    assert thread.title == "What's the weather like today?"


async def test_touch_truncates_long_first_message(store):
    long_msg = "x" * 100
    await store.touch("t1", "user-1", long_msg)
    thread = await store.get("t1")
    assert len(thread.title) <= 61  # 60 chars + ellipsis
    assert thread.title.endswith("…")


async def test_touch_again_keeps_title_bumps_updated_at(store):
    await store.touch("t1", "user-1", "first message")
    original_updated = (await store.get("t1")).updated_at
    await store.touch("t1", "user-1", "a completely different message")
    thread = await store.get("t1")
    assert thread.title == "first message"
    assert thread.updated_at >= original_updated


async def test_touch_does_not_let_other_user_hijack_thread(store):
    await store.touch("t1", "user-1", "owned by user-1")
    await store.touch("t1", "user-2", "attempted takeover")
    thread = await store.get("t1")
    assert thread.user_id == "user-1"


async def test_list_for_user_only_returns_own_threads_newest_first(store):
    await store.touch("t1", "user-1", "first")
    await store.touch("t2", "user-2", "other user's thread")
    await store.touch("t3", "user-1", "second")
    threads = await store.list_for_user("user-1")
    assert [t.id for t in threads] == ["t3", "t1"]


async def test_delete_requires_ownership(store):
    await store.touch("t1", "user-1", "mine")
    assert await store.delete("t1", "user-2") is False
    assert await store.delete("t1", "user-1") is True
    assert await store.get("t1") is None


async def test_rename_requires_ownership(store):
    await store.touch("t1", "user-1", "original")
    assert await store.rename("t1", "user-2", "hijacked title") is False
    assert await store.rename("t1", "user-1", "renamed title") is True
    assert (await store.get("t1")).title == "renamed title"
