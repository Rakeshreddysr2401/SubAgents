"""InMemoryUserStore: same method surface as the Postgres-backed store."""

import pytest

from src.services.user_store import EmailAlreadyExists, InMemoryUserStore


@pytest.fixture
def store():
    return InMemoryUserStore()


async def test_create_and_get_by_email(store):
    user = await store.create("Alice@Example.com", "hashed")
    assert user.email == "alice@example.com"  # normalized to lowercase
    fetched = await store.get_by_email("ALICE@example.com")
    assert fetched.id == user.id


async def test_duplicate_email_rejected(store):
    await store.create("bob@example.com", "hashed")
    with pytest.raises(EmailAlreadyExists):
        await store.create("bob@example.com", "other-hash")


async def test_get_by_id(store):
    user = await store.create("carol@example.com", "hashed")
    assert (await store.get_by_id(user.id)).email == "carol@example.com"
    assert await store.get_by_id("nonexistent") is None


async def test_update_password(store):
    user = await store.create("dave@example.com", "old-hash")
    await store.update_password(user.id, "new-hash")
    assert (await store.get_by_id(user.id)).password_hash == "new-hash"


async def test_delete(store):
    user = await store.create("erin@example.com", "hashed")
    await store.delete(user.id)
    assert await store.get_by_id(user.id) is None
