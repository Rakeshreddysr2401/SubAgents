"""Shopping store: user scoping, name matching, purchase toggling."""

from src.services.shopping_store import InMemoryShoppingStore


async def test_add_and_list_scoped_by_user():
    store = InMemoryShoppingStore()
    await store.add("alice", "soap")
    await store.add("bob", "shampoo")

    items = await store.list_for_user("alice")
    assert [i.name for i in items] == ["soap"]


async def test_list_excludes_purchased_when_asked():
    store = InMemoryShoppingStore()
    soap = await store.add("alice", "soap")
    await store.add("alice", "rice")
    await store.set_purchased(soap.id, "alice", True)

    unpurchased = await store.list_for_user("alice", include_purchased=False)
    assert [i.name for i in unpurchased] == ["rice"]


async def test_find_by_name_case_insensitive_contains():
    store = InMemoryShoppingStore()
    await store.add("alice", "Chintol Soap")

    assert len(await store.find_by_name("alice", "soap")) == 1
    assert len(await store.find_by_name("alice", "CHINTOL")) == 1
    assert await store.find_by_name("alice", "shampoo") == []
    assert await store.find_by_name("bob", "soap") == []  # other user


async def test_set_purchased_and_remove_enforce_ownership():
    store = InMemoryShoppingStore()
    item = await store.add("alice", "soap")

    assert not await store.set_purchased(item.id, "bob", True)
    assert await store.set_purchased(item.id, "alice", True)
    assert not await store.remove(item.id, "bob")
    assert await store.remove(item.id, "alice")
    assert await store.list_for_user("alice") == []
