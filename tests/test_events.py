"""Wake-word event fan-out."""

import asyncio
from types import SimpleNamespace

from src.api.events import broadcast_event


def _app_with_subscribers(n: int):
    subs = {asyncio.Queue() for _ in range(n)}
    app = SimpleNamespace(state=SimpleNamespace(event_subscribers=subs))
    return app, subs


async def test_broadcast_reaches_every_subscriber():
    app, subs = _app_with_subscribers(3)
    count = broadcast_event(app, "start_voice")
    assert count == 3
    for q in subs:
        assert q.get_nowait() == "start_voice"


async def test_broadcast_with_no_subscribers_is_noop():
    app, _ = _app_with_subscribers(0)
    assert broadcast_event(app, "start_voice") == 0


async def test_threadsafe_bridge_delivers_from_another_thread():
    """Mirror the in-process listener: an audio thread hands the event to the
    loop via call_soon_threadsafe, which fans it out."""
    import threading

    app, subs = _app_with_subscribers(2)
    loop = asyncio.get_running_loop()

    def audio_thread():
        loop.call_soon_threadsafe(broadcast_event, app, "start_voice")

    threading.Thread(target=audio_thread).start()
    # Give the scheduled callback a tick to run
    await asyncio.sleep(0.05)
    for q in subs:
        assert q.get_nowait() == "start_voice"
