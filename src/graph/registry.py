"""Central agent registry — the single source of truth for the swarm's shape.

One AgentSpec per agent. build_swarm_graph() derives everything from this
table: agent construction, tool sets, handoff wiring, vision/MCP behavior.
Adding an agent = a prompt module + a tool list + ONE entry here (plus
routing-rule lines in the other prompts, which only the LLM reads) — see
CLAUDE.md "Adding a New Agent".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.commons.constants import (
    CONVERSATION,
    DINEOUT,
    INSTAMART,
    PLANNER,
    SWIGGY,
    TRACKER,
)
from src.prompts import conversation as conversation_prompt
from src.prompts import dineout as dineout_prompt
from src.prompts import instamart as instamart_prompt
from src.prompts import planner as planner_prompt
from src.prompts import swiggy as swiggy_prompt
from src.prompts import tracker as tracker_prompt


@dataclass(frozen=True)
class AgentSpec:
    name: str
    # Module exposing build_prompt() and, for MCP-backed agents, UNAVAILABLE_NOTE.
    prompt_module: object
    # Resolved at graph-build time (AFTER apply_mcp_tools mutates the lists).
    tools: Callable[[], list]
    # mcp_providers key driving the provider-down prompt swap, or None.
    mcp_provider: str | None = None
    # Vision agents keep camera frames; others get StripImagesMiddleware.
    vision: bool = False
    # Deep agents are built with deepagents.create_deep_agent (planner).
    deep: bool = False
    # Peers this agent must NOT get a transfer tool for (default: all peers).
    no_handoff_to: tuple[str, ...] = ()


def _tools(attr: str) -> Callable[[], list]:
    """Late-bound tool list: src.tools' lists are mutated at startup by
    apply_mcp_tools, so they must be read at build time, not import time."""
    def resolve() -> list:
        import src.tools as tools_pkg

        return list(getattr(tools_pkg, attr))

    return resolve


AGENT_SPECS: dict[str, AgentSpec] = {
    CONVERSATION: AgentSpec(
        CONVERSATION, conversation_prompt, _tools("CONVERSATION_TOOLS"),
        vision=True,  # the only agent that sees camera frames
    ),
    SWIGGY: AgentSpec(
        SWIGGY, swiggy_prompt, _tools("SWIGGY_TOOLS"),
        mcp_provider="swiggy_food",
    ),
    INSTAMART: AgentSpec(
        INSTAMART, instamart_prompt, _tools("INSTAMART_TOOLS"),
        mcp_provider="swiggy_instamart",
    ),
    DINEOUT: AgentSpec(
        DINEOUT, dineout_prompt, _tools("DINEOUT_TOOLS"),
        mcp_provider="swiggy_dineout",
        no_handoff_to=(TRACKER,),  # reservations aren't deliveries
    ),
    TRACKER: AgentSpec(
        TRACKER, tracker_prompt, _tools("TRACKER_TOOLS"),
        no_handoff_to=(DINEOUT,),  # nothing to book from a delivery status
    ),
    PLANNER: AgentSpec(
        PLANNER, planner_prompt, lambda: [],  # deepagents ships its own tools
        deep=True,
    ),
}
