"""Reminder tools — create, list and cancel scheduled reminders.

The scheduler (src/services/reminder_scheduler.py) fires due reminders to the
user's browser as `{"type": "reminder"}` events (toast + spoken aloud).
"""

from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.configs.logging_config import get_logger
from src.services.event_broker import get_broker
from src.services.reminder_store import get_reminder_store

logger = get_logger(__name__)


def _user_id(config: RunnableConfig) -> str:
    return config.get("configurable", {}).get("user_id", "default_user")


def _parse_due_at(due_at: str) -> datetime | str:
    """ISO-8601 string → aware datetime, or a friendly error string."""
    try:
        parsed = datetime.fromisoformat(due_at)
    except ValueError:
        return (
            f"Could not parse '{due_at}' as a date/time. Pass an ISO-8601 "
            "datetime like 2026-07-07T17:00:00 (resolve relative times using "
            "the current date & time in your instructions)."
        )
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()  # naive → the server's local timezone
    if parsed <= datetime.now(timezone.utc):
        return (
            f"That time ({parsed.isoformat()}) is in the past. Reminders must "
            "be in the future — double-check against the current date & time."
        )
    return parsed


@tool
async def create_reminder(text: str, due_at: str, config: RunnableConfig) -> str:
    """Schedule a reminder for the user. They'll get a notification (text +
    voice) in the browser when it's due.

    Args:
        text: What to remind the user about, e.g. "go to the movie".
        due_at: When to fire, as an ISO-8601 datetime (e.g. 2026-07-07T17:00:00).
            Resolve relative times ("at 5", "in 20 minutes", "tomorrow morning")
            using the current date & time from your instructions.
    """
    parsed = _parse_due_at(due_at)
    if isinstance(parsed, str):
        return parsed
    user_id = _user_id(config)
    reminder = await get_reminder_store().create(user_id, text.strip(), parsed)
    get_broker().broadcast({"type": "reminders_updated"}, user_id)
    logger.info("Reminder %s created for user=%s at %s", reminder.id, user_id, parsed.isoformat())
    local = parsed.astimezone()
    return (
        f"Reminder set for {local.strftime('%A %d %B %Y, %I:%M %p')} "
        f"({local.isoformat()}): {text.strip()} [id: {reminder.id}]"
    )


@tool
async def list_reminders(config: RunnableConfig) -> str:
    """List the user's reminders — upcoming ones first, then recent past ones."""
    reminders = await get_reminder_store().list_for_user(_user_id(config))
    if not reminders:
        return "No reminders set."
    lines = []
    for r in reminders:
        local = r.due_at.astimezone()
        lines.append(
            f"- [{r.status}] {r.text} — {local.strftime('%a %d %b %Y, %I:%M %p')} (id: {r.id})"
        )
    return "\n".join(lines)


@tool
async def cancel_reminder(reminder_id: str, config: RunnableConfig) -> str:
    """Cancel a pending reminder by its id (get ids from list_reminders)."""
    user_id = _user_id(config)
    if await get_reminder_store().cancel(reminder_id.strip(), user_id):
        get_broker().broadcast({"type": "reminders_updated"}, user_id)
        return "Reminder cancelled."
    return "No pending reminder found with that id (it may have already fired or been cancelled)."
