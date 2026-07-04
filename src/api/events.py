"""Wake-word event channel + health check.

GET  /events         SSE stream the browser subscribes to
POST /trigger_voice  called by wake_word.py to wake the UI mic
GET  /health

Events fan out to *every* connected subscriber (each gets its own queue), so a
trigger reaches all open tabs and is never swallowed by a single stale
connection. The registry lives on app.state.event_subscribers.
"""

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


def _subscribers(request: Request) -> set:
    return request.app.state.event_subscribers


def broadcast_event(app, data: str) -> int:
    """Fan out an event to every connected /events subscriber. Returns the count.

    Must be called on the app's event loop (use loop.call_soon_threadsafe from
    other threads, e.g. the in-process wake-word listener)."""
    subscribers = app.state.event_subscribers
    for queue in list(subscribers):
        queue.put_nowait(data)
    return len(subscribers)


@router.get("/events")
async def events(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers(request).add(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
        finally:
            _subscribers(request).discard(queue)

    return EventSourceResponse(event_generator())


@router.post("/trigger_voice")
async def trigger_voice(request: Request):
    count = broadcast_event(request.app, "start_voice")
    return {"status": "triggered", "subscribers": count}


@router.get("/health")
async def health():
    return {"status": "ok", "service": "subagents"}
