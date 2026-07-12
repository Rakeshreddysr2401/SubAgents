CONVERSATION = "conversation"
SWIGGY = "swiggy"
INSTAMART = "instamart"
DINEOUT = "dineout"
TRACKER = "tracker"
PLANNER = "planner"

AGENTS = {CONVERSATION, SWIGGY, INSTAMART, DINEOUT, TRACKER, PLANNER}

AGENT_DESCRIPTIONS = {
    CONVERSATION: "general conversation, web search, system info, and visual/webcam tasks",
    SWIGGY: "restaurant food ordering: search, menus, cart management, and order placement",
    INSTAMART: "grocery and household-essentials ordering (Swiggy Instamart quick commerce)",
    DINEOUT: "dine-in restaurant discovery and table reservations (Swiggy Dineout)",
    TRACKER: "delivery status and order tracking (food and grocery)",
    PLANNER: "decomposing complex multi-step requests that span several specialists into a tracked plan",
}

# Tools gated behind a human-in-the-loop approval (see src/graph/swarm.py's
# HumanInTheLoopMiddleware wiring and src/api/chat.py's interrupt handling).
# `True` allows the full approve/edit/reject/respond decision set.
#
# Gating is by tool name and agent-agnostic, so `confirm_order` (the shared
# order-placement name on both the food and instamart MCP servers) is caught
# no matter which agent calls it — this is the spend guardrail: enforcement
# at the tool boundary, not in prompts. src/app.py logs every loaded MCP
# tool's name at startup so further cart-mutation names can be enumerated and
# added once the MCP servers are reachable.
GATED_TOOL_NAMES: dict = {
    "open_mac_app": True,
    # Swiggy order-placement / commitment tools (names confirmed from the
    # live MCP servers, logged at startup). These are the irreversible
    # spend/commit steps — placing pauses for human approval. Cart-building
    # tools (update_cart, apply_coupon, …) stay ungated so ordering isn't
    # a pause-fest.
    "confirm_order": True,       # final confirm, all three providers
    "place_food_order": True,    # swiggy_food — places the food order
    "checkout": True,            # swiggy_instamart — grocery checkout/payment
    "book_table": True,          # swiggy_dineout — commits a reservation
    # Not an approval — a structured question. The interrupt ships
    # {question, options} to the browser, the ChoiceCard renders buttons,
    # and the user's pick returns as the tool result via "respond".
    "ask_user_choice": {"allowed_decisions": ["respond", "reject"]},
}
