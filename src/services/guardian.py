"""Guardian mode — the assistant keeps an eye on the camera and speaks up.

While enabled for a user, a lifespan-owned loop periodically pulls the latest
webcam frame (the browser streams frames over /ws/frames regardless of chat
activity) and asks the vision model whether anything looks concerning compared
to the previous observation. Concerns become `{"type": "guardian_alert"}`
events (persistent toast + spoken aloud in the browser), rate-limited by a
cooldown so one incident doesn't spam.

State lives in Redis:
  guardian:enabled          — set of user_ids with guardian on (O(1) iteration)
  guardian:{user_id}        — JSON {thread_id, since, last_observation,
                              last_alert_at, no_frame_notified}
"""

import asyncio
import json
import time

from langchain_core.messages import HumanMessage

from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.services import redis_client
from src.services.frame_buffer import get_latest_frame

logger = get_logger(__name__)

_ENABLED_SET = "guardian:enabled"


def _state_key(user_id: str) -> str:
    return f"guardian:{user_id}"


_PROMPT = """You are a home guardian watching a camera feed for one household.
Previous observation: {previous}

Look at the current frame. Reply ONLY with JSON, no other text:
{{"observation": "<one sentence: what you see now>", "concern": true/false, "message": "<if concern: a short alert for the user, else empty>"}}

A concern is something genuinely worth interrupting the user for: a person who
shouldn't be there, smoke/fire, someone who has fallen, a pet in trouble, a
door/window newly open. Ordinary scenes, the usual occupants working, or an
empty room are NOT concerns."""


async def enable_guardian(user_id: str, thread_id: str) -> None:
    redis = redis_client.get_redis()
    state = {
        "thread_id": thread_id,
        "since": time.time(),
        "last_observation": None,
        "last_alert_at": 0.0,
        "no_frame_notified": False,
    }
    await redis.set(_state_key(user_id), json.dumps(state))
    await redis.sadd(_ENABLED_SET, user_id)
    logger.info("Guardian enabled for user=%s (thread=%s)", user_id, thread_id)


async def disable_guardian(user_id: str) -> None:
    redis = redis_client.get_redis()
    await redis.srem(_ENABLED_SET, user_id)
    await redis.delete(_state_key(user_id))
    logger.info("Guardian disabled for user=%s", user_id)


async def guardian_state(user_id: str) -> dict | None:
    raw = await redis_client.get_redis().get(_state_key(user_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_json(text: str) -> dict | None:
    """Tolerant parse: find the first {...} block in the model's reply."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def _watch_one(user_id: str, broker, llm, now: float) -> None:
    redis = redis_client.get_redis()
    state = await guardian_state(user_id)
    if state is None:
        await redis.srem(_ENABLED_SET, user_id)  # orphaned set entry
        return

    frame = await get_latest_frame(state["thread_id"])
    if not frame:
        if not state.get("no_frame_notified"):
            broker.broadcast({"type": "guardian_status", "status": "no_frame"}, user_id)
            state["no_frame_notified"] = True
            await redis.set(_state_key(user_id), json.dumps(state))
        return
    state["no_frame_notified"] = False  # frames resumed → re-arm the notice

    prompt = _PROMPT.format(previous=state.get("last_observation") or "none (first look)")
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{frame}"}},
        ]
    )
    reply = await llm.ainvoke([message])
    text = reply.content if isinstance(reply.content, str) else str(reply.content)
    parsed = _extract_json(text)
    if parsed is None:
        logger.warning("Guardian: unparseable vision reply for user=%s: %.120s", user_id, text)
        return

    state["last_observation"] = str(parsed.get("observation") or "")[:300]

    settings = get_settings()
    cooldown_over = now - float(state.get("last_alert_at") or 0) > settings.guardian_alert_cooldown_seconds
    if parsed.get("concern") and cooldown_over:
        alert = str(parsed.get("message") or "Something in the camera view needs your attention.")
        broker.broadcast(
            {
                "type": "guardian_alert",
                "message": alert,
                "thread_id": state["thread_id"],
                "at": now,
            },
            user_id,
        )
        state["last_alert_at"] = now
        logger.info("Guardian alert for user=%s: %s", user_id, alert)

    await redis.set(_state_key(user_id), json.dumps(state))


async def guardian_tick(broker, llm=None, now: float | None = None) -> None:
    """One pass over all guardian-enabled users. LLM injectable for tests."""
    redis = redis_client.get_redis()
    user_ids = await redis.smembers(_ENABLED_SET)
    if not user_ids:
        return
    if llm is None:
        from src.configs.llm import get_vision_llm

        llm = get_vision_llm()  # the dedicated VLM (mac-mini llama.cpp)
    now = now if now is not None else time.time()
    for user_id in user_ids:
        uid = user_id if isinstance(user_id, str) else user_id.decode()
        try:
            await _watch_one(uid, broker, llm, now)
        except Exception as e:
            logger.warning("Guardian tick failed for user=%s: %s", uid, e)


async def guardian_loop(broker, interval_seconds: float) -> None:
    """Run guardian_tick forever; one bad tick never kills the loop."""
    while True:
        try:
            await guardian_tick(broker)
        except Exception as e:
            logger.warning("Guardian tick failed: %s", e)
        await asyncio.sleep(interval_seconds)
