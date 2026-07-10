"""Per-user reminders REST (backs the Reminders panel).

Creation happens through the create_reminder LangChain tool (the assistant
sets reminders conversationally); the panel only lists and cancels.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.deps import rate_limited_user
from src.models.schema import ReminderOut
from src.services.event_broker import get_broker

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _to_out(r) -> ReminderOut:
    return ReminderOut(
        id=r.id,
        text=r.text,
        due_at=r.due_at.isoformat(),
        status=r.status,
        created_at=r.created_at.isoformat(),
        fired_at=r.fired_at.isoformat() if r.fired_at else None,
    )


@router.get("", response_model=list[ReminderOut])
async def list_reminders(request: Request, user_id: str = Depends(rate_limited_user)):
    reminders = await request.app.state.reminder_store.list_for_user(user_id)
    return [_to_out(r) for r in reminders]


@router.delete("/{reminder_id}")
async def cancel_reminder(
    reminder_id: str, request: Request, user_id: str = Depends(rate_limited_user)
):
    ok = await request.app.state.reminder_store.cancel(reminder_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No pending reminder with that id")
    get_broker().broadcast({"type": "reminders_updated"}, user_id)
    return {"status": "cancelled"}
