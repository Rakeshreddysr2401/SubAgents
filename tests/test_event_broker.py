"""Per-user routing of the server-push event broker."""

import json

from src.services.event_broker import EventBroker, get_broker, reset_broker


async def test_user_scoped_event_only_reaches_owner():
    broker = EventBroker()
    q_alice = broker.subscribe("alice")
    q_bob = broker.subscribe("bob")

    count = broker.broadcast({"type": "reminder", "reminder": {"text": "stretch"}}, user_id="alice")

    assert count == 1
    assert json.loads(q_alice.get_nowait())["type"] == "reminder"
    assert q_bob.empty()


async def test_broadcast_all_reaches_every_user():
    broker = EventBroker()
    queues = [broker.subscribe("alice"), broker.subscribe("alice"), broker.subscribe("bob")]

    count = broker.broadcast({"type": "start_voice"})

    assert count == 3
    for q in queues:
        assert not q.empty()


async def test_same_user_multiple_tabs_all_receive():
    broker = EventBroker()
    tab1 = broker.subscribe("alice")
    tab2 = broker.subscribe("alice")

    count = broker.broadcast({"type": "shopping_updated"}, user_id="alice")

    assert count == 2
    assert not tab1.empty() and not tab2.empty()


async def test_unsubscribe_stops_delivery_and_is_idempotent():
    broker = EventBroker()
    q = broker.subscribe("alice")
    broker.unsubscribe(q)
    broker.unsubscribe(q)  # second call must not raise

    assert broker.broadcast({"type": "start_voice"}) == 0
    assert q.empty()


async def test_singleton_reset_seam():
    reset_broker()
    first = get_broker()
    assert get_broker() is first
    reset_broker()
    assert get_broker() is not first
