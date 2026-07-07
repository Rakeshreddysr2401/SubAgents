"""Server-push event fan-out (wake word + JSON payload contract)."""

import asyncio
import json
import threading

from src.services.event_broker import EventBroker


async def test_broadcast_reaches_every_subscriber():
    broker = EventBroker()
    queues = [broker.subscribe(f"user-{i}") for i in range(3)]
    count = broker.broadcast({"type": "start_voice"})
    assert count == 3
    for q in queues:
        assert json.loads(q.get_nowait()) == {"type": "start_voice"}


async def test_broadcast_with_no_subscribers_is_noop():
    broker = EventBroker()
    assert broker.broadcast({"type": "start_voice"}) == 0


async def test_threadsafe_bridge_delivers_from_another_thread():
    """Mirror the in-process wake-word listener: an audio thread hands the
    event to the loop via call_soon_threadsafe, which fans it out."""
    broker = EventBroker()
    queues = [broker.subscribe("u1"), broker.subscribe("u2")]
    loop = asyncio.get_running_loop()

    def audio_thread():
        loop.call_soon_threadsafe(broker.broadcast, {"type": "start_voice"})

    threading.Thread(target=audio_thread).start()
    await asyncio.sleep(0.05)
    for q in queues:
        assert json.loads(q.get_nowait()) == {"type": "start_voice"}
