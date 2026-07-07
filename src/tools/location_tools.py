"""Location tool — resolve the user's browser geolocation to an address.

The browser sends {lat, lon} with each /chat call (if the user granted
permission); chat.py places it in config["configurable"]["location"].
Reverse geocoding uses OpenStreetMap Nominatim, which requires a User-Agent
and at most 1 request/second — enforced here with a module lock, plus a
24h Redis cache keyed by rounded coordinates so repeat queries never hit
the network. Failures degrade to raw coordinates, never raise.
"""

import asyncio
import time

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.configs.logging_config import get_logger
from src.services import redis_client

logger = get_logger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "SubAgents/0.2 (personal assistant; contact: local dev)"
_CACHE_TTL_SECONDS = 24 * 3600
_MIN_INTERVAL_SECONDS = 1.1

_rate_lock = asyncio.Lock()
_last_call = 0.0


async def reverse_geocode(lat: float, lon: float) -> str:
    coords = f"{lat:.5f}, {lon:.5f}"
    cache_key = f"geocode:{round(lat, 3)}:{round(lon, 3)}"
    redis = redis_client.get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            return cached if isinstance(cached, str) else cached.decode()
    except Exception as e:
        logger.warning("geocode cache read failed: %s", e)

    global _last_call
    try:
        async with _rate_lock:
            wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            _last_call = time.monotonic()
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    _NOMINATIM_URL,
                    params={"lat": lat, "lon": lon, "format": "jsonv2"},
                    headers={"User-Agent": _USER_AGENT},
                )
                resp.raise_for_status()
                display_name = resp.json().get("display_name")
    except Exception as e:
        logger.warning("reverse geocode failed: %s", e)
        return coords

    if not display_name:
        return coords
    result = f"{display_name} ({coords})"
    try:
        await redis.set(cache_key, result, ex=_CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning("geocode cache write failed: %s", e)
    return result


@tool
async def get_current_location(config: RunnableConfig) -> str:
    """Get the user's current location (address + coordinates) from their
    device. Use it for "near me" queries, weather, or checking that a food
    delivery address makes sense."""
    location = config.get("configurable", {}).get("location")
    if not location:
        return (
            "Location not available — the user hasn't granted browser location "
            "access (or the fix timed out). Ask them to allow location access "
            "if it matters."
        )
    return await reverse_geocode(location["lat"], location["lon"])
