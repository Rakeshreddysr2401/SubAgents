"""Shared FastAPI dependencies and helpers for pulling resources off app.state."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request

from src.api.auth import get_user_id
from src.configs.settings import get_settings
from src.services.rate_limit import enforce_rate_limit


async def rate_limited_user(user_id: str = Depends(get_user_id)) -> str:
    """get_user_id + the shared "api" rate-limit bucket for cheap CRUD routes.

    Chat/upload/auth keep their own tighter buckets; this one covers
    threads/reminders/shopping/music/guardian panel traffic.
    """
    await enforce_rate_limit("api", user_id, limit=get_settings().api_rate_limit_per_minute)
    return user_id


def validate_thread_id(tid: str) -> str:
    """Accept UUID format or any string up to 64 chars; reject everything else."""
    try:
        return str(UUID(tid))
    except ValueError:
        pass
    if len(tid) > 64:
        raise HTTPException(status_code=400, detail="Invalid thread_id: too long")
    return tid


def get_graph(request: Request):
    return request.app.state.graph


def get_redis(request: Request):
    return request.app.state.redis


def get_qdrant(request: Request):
    return request.app.state.qdrant
