"""Fixed-window per-user rate limiting backed by Redis.

A minimal sliding-ish window: one counter key per (scope, user, minute-bucket)
with a 60s TTL. Good enough for a personal assistant; swap for a token bucket
if you need burst smoothing.
"""

import time

from fastapi import HTTPException

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.services import redis_client

logger = get_logger(__name__)


async def enforce_rate_limit(scope: str, user_id: str, limit: int | None = None) -> None:
    """Raise HTTP 429 if `user_id` exceeded the per-minute limit for `scope`.

    Fails open: if Redis is unavailable the request is allowed rather than
    breaking the assistant (the graph itself only needs Postgres).

    `limit` overrides the default RATE_LIMIT_PER_MINUTE for cheaper scopes
    (e.g. the shared "api" bucket uses API_RATE_LIMIT_PER_MINUTE).
    """
    if limit is None:
        limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    bucket = int(time.time()) // 60
    key = f"ratelimit:{scope}:{user_id}:{bucket}"
    redis = redis_client.get_redis()
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except Exception as e:
        logger.warning("rate limit check skipped (Redis error): %s", e)
        return
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({limit}/min). Please slow down.",
        )
