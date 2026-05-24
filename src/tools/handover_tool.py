from typing import Literal
from langchain_core.tools import tool

HANDOVER_NAMES = {"handover"}


@tool("handover")
def handover(
    next_agent: Literal["supervisor", "conversation", "swiggy", "tracker"],
    reason: str = "",
    chain: bool = False,
) -> str:
    """Transfer the conversation to another agent.

    Sub-agents MUST use "supervisor" as next_agent when done and unsure where to go.
    Only the supervisor routes directly to sub-agents.

    Args:
        next_agent: Agent to route to.
        reason: Why this handover is happening (e.g. "order_placed", "cannot_answer").
        chain: True → next agent responds immediately in the same turn.
               Use for swiggy → tracker after placing an order.
    """
    return f"{next_agent}|{reason}|{str(chain).lower()}"
