"""Server-push event channel.

GET  /events         SSE stream the browser subscribes to (per-user routed)
POST /trigger_voice  called by wake_word.py to wake the UI mic

(/health lives in src/api/system.py alongside /status and /metrics.)

All event payloads are JSON objects with a "type" key (see docs/api.md for the
full contract). Fan-out is handled by src/services/event_broker.py — a
module-level singleton so tools and background loops can push events too.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from src.api.auth import get_user_id
from src.configs.settings import get_settings
from src.services import metrics
from src.services.event_broker import get_broker

router = APIRouter()


@router.get("/events")
async def events(user_id: str = Depends(get_user_id)):
    broker = get_broker()
    cap = get_settings().events_max_connections_per_user
    if cap > 0 and broker.subscriber_count(user_id) >= cap:
        raise HTTPException(
            status_code=429,
            detail=f"Too many event streams open for this account (max {cap}).",
        )
    queue = broker.subscribe(user_id)
    metrics.adjust_gauge("sse_clients", 1)

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield {"data": data}
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
        finally:
            broker.unsubscribe(queue)
            metrics.adjust_gauge("sse_clients", -1)

    return EventSourceResponse(event_generator())


@router.post("/trigger_voice")
async def trigger_voice():
    count = get_broker().broadcast({"type": "start_voice"})
    return {"status": "triggered", "subscribers": count}
