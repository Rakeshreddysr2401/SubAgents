"""Guardian mode: no-frame notices, alerts, cooldown, resilience."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import guardian
from src.services.event_broker import EventBroker


@pytest.fixture(autouse=True)
def fake_redis():
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("src.services.redis_client.get_redis", return_value=redis):
        yield redis


def _llm_replying(text: str):
    llm = MagicMock()
    reply = MagicMock()
    reply.content = text
    llm.ainvoke = AsyncMock(return_value=reply)
    return llm


def _concern_reply(message: str = "Someone unfamiliar entered the room") -> str:
    return json.dumps({"observation": "a stranger walked in", "concern": True, "message": message})


def _calm_reply() -> str:
    return json.dumps({"observation": "an empty room", "concern": False, "message": ""})


async def test_enable_disable_round_trip():
    await guardian.enable_guardian("alice", "t1")
    state = await guardian.guardian_state("alice")
    assert state is not None and state["thread_id"] == "t1"

    await guardian.disable_guardian("alice")
    assert await guardian.guardian_state("alice") is None


async def test_no_frame_notifies_once():
    broker = EventBroker()
    q = broker.subscribe("alice")
    await guardian.enable_guardian("alice", "t1")

    with patch("src.services.guardian.get_latest_frame", new=AsyncMock(return_value=None)):
        await guardian.guardian_tick(broker, llm=_llm_replying(_calm_reply()))
        await guardian.guardian_tick(broker, llm=_llm_replying(_calm_reply()))

    events = []
    while not q.empty():
        events.append(json.loads(q.get_nowait()))
    assert events == [{"type": "guardian_status", "status": "no_frame"}]


async def test_concern_alerts_only_the_owner():
    broker = EventBroker()
    q_alice = broker.subscribe("alice")
    q_bob = broker.subscribe("bob")
    await guardian.enable_guardian("alice", "t1")

    with patch("src.services.guardian.get_latest_frame", new=AsyncMock(return_value="b64frame")):
        await guardian.guardian_tick(broker, llm=_llm_replying(_concern_reply()), now=1000.0)

    event = json.loads(q_alice.get_nowait())
    assert event["type"] == "guardian_alert"
    assert "unfamiliar" in event["message"]
    assert q_bob.empty()

    # The observation is remembered for the next comparison.
    state = await guardian.guardian_state("alice")
    assert "stranger" in state["last_observation"]


async def test_alert_cooldown_suppresses_repeat():
    broker = EventBroker()
    q = broker.subscribe("alice")
    await guardian.enable_guardian("alice", "t1")

    with patch("src.services.guardian.get_latest_frame", new=AsyncMock(return_value="b64frame")):
        await guardian.guardian_tick(broker, llm=_llm_replying(_concern_reply()), now=1000.0)
        await guardian.guardian_tick(broker, llm=_llm_replying(_concern_reply()), now=1020.0)  # within cooldown
        await guardian.guardian_tick(broker, llm=_llm_replying(_concern_reply()), now=2000.0)  # past cooldown

    alerts = []
    while not q.empty():
        event = json.loads(q.get_nowait())
        if event["type"] == "guardian_alert":
            alerts.append(event)
    assert len(alerts) == 2


async def test_llm_failure_never_crashes_tick():
    broker = EventBroker()
    q = broker.subscribe("alice")
    await guardian.enable_guardian("alice", "t1")
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("model down"))

    with patch("src.services.guardian.get_latest_frame", new=AsyncMock(return_value="b64frame")):
        await guardian.guardian_tick(broker, llm=llm)  # must not raise

    assert q.empty()


async def test_unparseable_reply_is_skipped():
    broker = EventBroker()
    q = broker.subscribe("alice")
    await guardian.enable_guardian("alice", "t1")

    with patch("src.services.guardian.get_latest_frame", new=AsyncMock(return_value="b64frame")):
        await guardian.guardian_tick(broker, llm=_llm_replying("I see a room, all fine!"))

    assert q.empty()
