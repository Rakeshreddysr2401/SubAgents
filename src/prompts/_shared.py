"""Shared prompt fragments for the Swiggy-backed ordering agents.

`mcp_unavailable_note(...)` builds the note the dynamic-prompt middleware
appends when an agent's MCP provider isn't serving tools. It is honest about
the cause so the model never tells the user to "try again later" for a
provider that was simply never connected — that needs a one-time login, not
patience (see src/services/mcp_providers.provider_unavailable_reason).
"""


def mcp_unavailable_note(service: str, capability: str, back_reason: str) -> callable:
    """Return an `unavailable_note(reason)` function for one ordering agent.

    service:    human label, e.g. "Food ordering".
    capability: what the agent normally does, e.g. "search restaurants,
                browse menus, or place orders".
    back_reason: the transfer_to_conversation reason tag.
    """

    def unavailable_note(reason: str) -> str:
        if reason == "expired":
            return f"""

IMPORTANT: {service} is paused because the Swiggy login has EXPIRED. You
cannot {capability} until it's renewed. Do not call any ordering tools and do
not say "try again later" — waiting will not fix it. Tell the user their
Swiggy login expired and they need to re-connect it: open Settings →
Integrations and run the Swiggy login (or `uv run python
scripts/swiggy_login.py`). It works again the moment they do. Then call
transfer_to_conversation(reason="{back_reason}").
"""
        # not_connected (or any other reason): never set up on this device.
        return f"""

IMPORTANT: {service} is not connected yet — no Swiggy account is linked on
this device, so you have no tools to {capability}. This is a one-time setup,
NOT a temporary outage: do not say "try again later". Instead, tell the user
warmly that to order they first need to connect their Swiggy account — open
Settings → Integrations and run the Swiggy login (or `uv run python
scripts/swiggy_login.py --verify`), and ordering lights up immediately. Offer
to help once it's connected. Then call
transfer_to_conversation(reason="{back_reason}").
"""

    return unavailable_note
