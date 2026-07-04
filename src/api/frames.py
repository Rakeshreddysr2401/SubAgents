"""WS /ws/frames — receive webcam frames from the browser (base64) or Jetson (binary)."""

import base64

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from src.configs.logging_config import get_logger
from src.services.frame_buffer import store_frame

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/frames")
async def video_frame_ws(ws: WebSocket, thread_id: str = Query(default=None)):
    await ws.accept()
    tid = thread_id or "default"
    logger.info("Video WebSocket connected: thread=%s", tid)

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
