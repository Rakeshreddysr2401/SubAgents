"""Active-order tracking state (Redis).

set_active_order stores the ID of the most recently placed Swiggy/Instamart
order per user so the tracker (and future background delivery polling) knows
which order "my order" refers to. TTL keeps stale IDs from lingering after a
delivery completes without an explicit clear.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.services.redis_client import get_redis

ACTIVE_ORDER_TTL_SECONDS = 3 * 3600


def _key(config: RunnableConfig) -> str:
    user_id = config.get("configurable", {}).get("user_id", "default_user")
    return f"active_order:{user_id}"


@tool
async def set_active_order(order_id: str | None, config: RunnableConfig) -> str:
    """Remember (or clear) the user's active delivery order.

    Call with the order ID right after successfully placing a food or grocery
    order so delivery tracking knows which order is live. Call with null/empty
    once the order is delivered to stop tracking it.

    Args:
        order_id: The order ID returned by the order placement, or null to clear.
    """
    redis = get_redis()
    key = _key(config)
    if order_id:
        await redis.set(key, order_id, ex=ACTIVE_ORDER_TTL_SECONDS)
        return f"Active order set to {order_id}."
    await redis.delete(key)
    return "Active order cleared."


async def get_active_order(user_id: str) -> str | None:
    """The user's active order ID, or None (used by status/tracking surfaces)."""
    value = await get_redis().get(f"active_order:{user_id}")
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)
