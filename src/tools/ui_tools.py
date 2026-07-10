"""Interactive UI tools — structured questions rendered as tappable components.

ask_user_choice rides the existing HITL interrupt rails: it is gated in
GATED_TOOL_NAMES with allowed_decisions ["respond", "reject"], so calling it
pauses the turn and ships {question, options} to the browser as a typed
interrupt. The frontend component registry (web/src/components/chat/
interrupts/) renders it as buttons + a free-text field; the user's selection
comes back as this tool's result via the "respond" decision — the tool body
below only runs if a decision type ever bypasses the gate.
"""

from langchain_core.tools import tool


@tool
def ask_user_choice(question: str, options: list[str]) -> str:
    """Ask the user to pick between a few concrete options, rendered as
    tappable buttons in their UI (with a free-text field for "something
    else"). The user's selection is returned as this tool's result.

    Use this whenever the user must choose or confirm a specific value —
    a delivery address, an item variant/size, a restaurant, a time slot —
    instead of listing the options in plain text.

    Args:
        question: The single decision the user must make, phrased briefly,
            e.g. "Which delivery address should I use?".
        options: 2–6 short, concrete choices, e.g. the saved addresses.
    """
    return "The choice dialog was skipped — ask the user in plain text instead."
