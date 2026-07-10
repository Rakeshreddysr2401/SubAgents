"""Per-user chat-thread listing: sidebar data backing the ChatGPT-style history.

Thread ownership lives in `chat_threads` (src/services/thread_store.py); the
actual messages live in the LangGraph checkpointer, keyed by thread_id.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.chat import read_graph_messages
from src.api.deps import rate_limited_user, validate_thread_id
from src.models.schema import RenameThreadRequest, ThreadOut

router = APIRouter(prefix="/threads", tags=["threads"])


def _to_out(thread) -> ThreadOut:
    return ThreadOut(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at.isoformat(),
        updated_at=thread.updated_at.isoformat(),
    )


@router.get("", response_model=list[ThreadOut])
async def list_threads(request: Request, user_id: str = Depends(rate_limited_user)):
    threads = await request.app.state.thread_store.list_for_user(user_id)
    return [_to_out(t) for t in threads]


@router.get("/{thread_id}/messages")
async def thread_messages(
    thread_id: str, request: Request, user_id: str = Depends(rate_limited_user)
):
    tid = validate_thread_id(thread_id)
    thread = await request.app.state.thread_store.get(tid)
    if thread is None or thread.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = await read_graph_messages(request.app.state.graph, tid)
    return {"thread_id": tid, "title": thread.title, "messages": messages}


@router.patch("/{thread_id}", response_model=ThreadOut)
async def rename_thread(
    thread_id: str,
    req: RenameThreadRequest,
    request: Request,
    user_id: str = Depends(rate_limited_user),
):
    tid = validate_thread_id(thread_id)
    ok = await request.app.state.thread_store.rename(tid, user_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found")
    thread = await request.app.state.thread_store.get(tid)
    return _to_out(thread)


@router.delete("/{thread_id}")
async def delete_thread(thread_id: str, request: Request, user_id: str = Depends(rate_limited_user)):
    tid = validate_thread_id(thread_id)
    ok = await request.app.state.thread_store.delete(tid, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"status": "ok"}
