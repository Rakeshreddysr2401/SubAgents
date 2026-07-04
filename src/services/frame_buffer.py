"""Redis-backed latest-frame buffer, keyed by thread_id.

Frames are base64-encoded JPEG strings sent from the browser via WebSocket.
Only the most recent frame per thread is retained, with a TTL so a stopped
camera stops serving stale frames (a correctness win for a visual assistant)
and state survives app restarts.
"""

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.services import redis_client

logger = get_logger(__name__)


def _key(thread_id: str) -> str:
    return f"frame:{thread_id}"


async def store_frame(thread_id: str, base64_jpeg: str) -> None:
    """Store the absolute latest frame for a thread with a TTL."""
    await redis_client.get_redis().set(
        _key(thread_id), base64_jpeg, ex=get_settings().frame_ttl_seconds
    )


async def get_latest_frame(thread_id: str) -> str | None:
    """Return the latest frame (base64 string) or None if none exist / expired."""
    return await redis_client.get_redis().get(_key(thread_id))


async def clear_frame(thread_id: str) -> None:
    await redis_client.get_redis().delete(_key(thread_id))
