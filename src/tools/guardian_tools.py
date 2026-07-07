"""Guardian tools — voice control for guardian mode ("watch my room").

Shares state with the UI shield toggle (src/api/guardian.py); both broadcast
guardian_status events so toggle and conversation stay in sync.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.services import guardian
from src.services.event_broker import get_broker


def _ids(config: RunnableConfig) -> tuple[str, str]:
    configurable = config.get("configurable", {})
    return (
        configurable.get("user_id", "default_user"),
        configurable.get("thread_id", "default"),
    )


@tool
async def enable_guardian(config: RunnableConfig) -> str:
    """Turn on guardian mode: keep watching the user's camera and alert them
    (notification + voice) if something concerning happens. The camera must be
    on and streaming for this to see anything."""
    user_id, thread_id = _ids(config)
    await guardian.enable_guardian(user_id, thread_id)
    get_broker().broadcast({"type": "guardian_status", "status": "enabled"}, user_id)
    return (
        "Guardian mode is on — I'll keep an eye on the camera and alert you if "
        "something looks wrong. Make sure the camera stays on."
    )


@tool
async def disable_guardian(config: RunnableConfig) -> str:
    """Turn guardian mode off."""
    user_id, _ = _ids(config)
    await guardian.disable_guardian(user_id)
    get_broker().broadcast({"type": "guardian_status", "status": "disabled"}, user_id)
    return "Guardian mode is off."
