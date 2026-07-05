"""WS /ws/frames — receive webcam frames from the browser (base64) or Jetson (binary).

Auth: the browser's WS handshake carries the `access_token` cookie automatically
(same-origin). Non-browser clients (e.g. a Jetson) can pass `?token=<jwt>`
instead. Connections are rejected before accept() if unauthenticated, or if the
thread already belongs to a different user (best-effort: a brand-new thread_id
has no owner row yet, so it's allowed through and gets attributed on first
`/chat` call via thread_store.touch).
"""

import base64

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.api.auth import DEFAULT_USER
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.services import security
from src.services.frame_buffer import store_frame

logger = get_logger(__name__)
router = APIRouter()


def _authenticate(ws: WebSocket) -> str | None:
    """Returns the user_id for this connection, or None if unauthenticated."""
    settings = get_settings()
    if settings.auth_disabled:
        return DEFAULT_USER
    token = ws.cookies.get("access_token") or ws.query_params.get("token")
    if not token:
        return None
    try:
        payload = security.decode_token(token, security.ACCESS)
    except jwt.PyJWTError:
        return None
    return payload.get("sub")


@router.websocket("/ws/frames")
async def video_frame_ws(ws: WebSocket, thread_id: str = Query(default=None)):
    user_id = _authenticate(ws)
    if user_id is None:
        await ws.close(code=4401)
        return

    tid = thread_id or "default"
    thread = await ws.app.state.thread_store.get(tid)
    if thread is not None and thread.user_id != user_id:
        await ws.close(code=4403)
        return

    await ws.accept()
    logger.info("Video WebSocket connected: thread=%s user=%s", tid, user_id)

    try:
        while True:
            message = await ws.receive()
            if "bytes" in message and message["bytes"] is not None:
                data = base64.b64encode(message["bytes"]).decode("utf-8")
                await store_frame(tid, data)
            elif "text" in message and message["text"] is not None:
                await store_frame(tid, message["text"])
    except WebSocketDisconnect:
        logger.info("Video WebSocket disconnected: thread=%s", tid)
    except Exception as e:
        logger.warning("Video WebSocket error: thread=%s, err=%s", tid, e)
