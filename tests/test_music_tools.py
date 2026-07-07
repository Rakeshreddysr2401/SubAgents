"""Music tools: station matching + user-routed browser events."""

import json

import pytest

from src.services.event_broker import get_broker, reset_broker
from src.tools.music_tools import _match_station, list_music_stations, play_music, stop_music


@pytest.fixture(autouse=True)
def fresh_broker():
    reset_broker()
    yield
    reset_broker()


def _config(user_id: str = "u1") -> dict:
    return {"configurable": {"user_id": user_id, "thread_id": "t1"}}


def test_match_station_by_substring():
    station = _match_station("groove")
    assert station is not None and "Groove Salad" in station["name"]


def test_unmatched_query_falls_back_to_first_station():
    station = _match_station("some totally unknown vibe")
    assert station is not None
    assert station["name"] == _match_station("")["name"]


def test_play_music_routes_event_to_user():
    q_u1 = get_broker().subscribe("u1")
    q_u2 = get_broker().subscribe("u2")

    result = play_music.invoke({"station_or_query": "groove"}, config=_config("u1"))

    assert "Playing" in result
    event = json.loads(q_u1.get_nowait())
    assert event["type"] == "music" and event["action"] == "play"
    assert event["url"].startswith("http")
    assert q_u2.empty()


def test_play_music_with_no_browser_says_so():
    result = play_music.invoke({"station_or_query": "groove"}, config=_config())
    assert "No browser" in result


def test_stop_music_broadcasts_stop():
    q = get_broker().subscribe("u1")
    stop_music.invoke({}, config=_config("u1"))
    assert json.loads(q.get_nowait()) == {"type": "music", "action": "stop"}


def test_list_music_stations_names_defaults():
    listing = list_music_stations.invoke({})
    assert "Groove Salad" in listing
