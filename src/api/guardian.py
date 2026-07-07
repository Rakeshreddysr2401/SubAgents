"""Guardian mode REST — the UI shield toggle. Voice control goes through the
enable_guardian/disable_guardian tools instead; both paths share
src/services/guardian.py state."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.api.auth import get_user_id
from src.api.deps import validate_thread_id
from src.services import guardian
from src.services.event_broker import get_broker

router = APIRouter(prefix="/guardian", tags=["guardian"])


class EnableGuardianRequest(BaseModel):
    thread_id: str


@router.post("/enable")
async def enable(
    req: EnableGuardianRequest, request: Request, user_id: str = Depends(get_user_id)
):
    tid = validate_thread_id(req.thread_id)
    # Same ownership rule as /ws/frames: an existing thread must be the
    # caller's; a brand-new thread_id has no owner row yet and is allowed.
    thread = await request.app.state.thread_store.get(tid)
    if thread is not None and thread.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your thread")
    await guardian.enable_guardian(user_id, tid)
    get_broker().broadcast({"type": "guardian_status", "status": "enabled"}, user_id)
    return {"status": "enabled", "thread_id": tid}


@router.post("/disable")
async def disable(user_id: str = Depends(get_user_id)):
    await guardian.disable_guardian(user_id)
    get_broker().broadcast({"type": "guardian_status", "status": "disabled"}, user_id)
    return {"status": "disabled"}


@router.get("/status")
async def status(user_id: str = Depends(get_user_id)):
    state = await guardian.guardian_state(user_id)
    if state is None:
        return {"enabled": False, "thread_id": None}
    return {"enabled": True, "thread_id": state["thread_id"]}
