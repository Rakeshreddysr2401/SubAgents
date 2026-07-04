"""Wake-word event channel + health check.

GET  /events         SSE stream the browser subscribes to
POST /trigger_voice  called by wake_word.py to wake the UI mic
GET  /health
"""

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.get("/events")
async def events(request: Request):
    queue: asyncio.Queue = request.app.state.event_queue

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await asyncio.wait_for(queue.get(), timeout=5.0)
                yield {"data": data}
            except asyncio.TimeoutError:
                yield {"comment": "heartbeat"}

    return EventSourceResponse(event_generator())


@router.post("/trigger_voice")
async def trigger_voice(request: Request):
    await request.app.state.event_queue.put("start_voice")
    return {"status": "triggered"}


@router.get("/health")
async def health():
    return {"status": "ok", "service": "subagents"}
