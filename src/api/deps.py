"""Shared FastAPI dependencies and helpers for pulling resources off app.state."""

from uuid import UUID

from fastapi import HTTPException, Request


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
