CONVERSATION = "conversation"
SWIGGY = "swiggy"
TRACKER = "tracker"
PLANNER = "planner"

AGENTS = {CONVERSATION, SWIGGY, TRACKER, PLANNER}

AGENT_DESCRIPTIONS = {
    CONVERSATION: "general conversation, web search, system info, and visual/webcam tasks",
    SWIGGY: "food ordering, restaurant search, menu browsing, cart management, and order placement",
    TRACKER: "delivery status and order tracking",
    PLANNER: "decomposing complex multi-step requests that span several specialists into a tracked plan",
}

# Tools gated behind a human-in-the-loop approval (see src/graph/swarm.py's
# HumanInTheLoopMiddleware wiring and src/api/chat.py's interrupt handling).
# `True` allows the full approve/edit/reject/respond decision set.
#
# Swiggy MCP's cart-mutation/order-placement tool names aren't visible in
# source (loaded dynamically at runtime from the remote MCP server, see
# src/tools/swiggy_mcp.py) — src/app.py logs each loaded tool's name at
# startup so they can be enumerated and added here once the MCP server is
# reachable.
GATED_TOOL_NAMES: dict[str, bool] = {
    "open_mac_app": True,
}
