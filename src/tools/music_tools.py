"""Music tools — control the browser's internet-radio player.

The tools don't play anything server-side: they broadcast `{"type": "music"}`
events to the user's browser, where MusicPanel owns the <audio> element.
Stations come from settings.music_stations (MUSIC_STATIONS env, JSON list).
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.configs.settings import get_settings
from src.services.event_broker import get_broker


def _user_id(config: RunnableConfig) -> str:
    return config.get("configurable", {}).get("user_id", "default_user")


def _match_station(query: str) -> dict | None:
    stations = get_settings().music_stations
    if not stations:
        return None
    needle = query.strip().lower()
    for station in stations:
        if needle and needle in station["name"].lower():
            return station
    return stations[0]  # no match → default to the first station


@tool
def play_music(station_or_query: str, config: RunnableConfig) -> str:
    """Start playing music in the user's browser (internet radio).

    Args:
        station_or_query: A station name or vibe, e.g. "groove salad",
            "something ambient", "radio paradise". An unrecognized query
            falls back to the default station.
    """
    station = _match_station(station_or_query)
    if station is None:
        return "No music stations are configured (set MUSIC_STATIONS)."
    delivered = get_broker().broadcast(
        {"type": "music", "action": "play", "url": station["url"], "station": station["name"]},
        _user_id(config),
    )
    if delivered == 0:
        return "No browser is connected to play music on."
    return f"Playing {station['name']} in the browser. (If it doesn't start, the user may need to tap the play button once — browser autoplay rules.)"


@tool
def stop_music(config: RunnableConfig) -> str:
    """Stop the music playing in the user's browser."""
    get_broker().broadcast({"type": "music", "action": "stop"}, _user_id(config))
    return "Music stopped."


@tool
def list_music_stations() -> str:
    """List the available music stations."""
    stations = get_settings().music_stations
    if not stations:
        return "No music stations are configured."
    return "Available stations:\n" + "\n".join(f"- {s['name']}" for s in stations)
