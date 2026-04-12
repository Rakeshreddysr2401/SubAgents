"""Memory store — disabled.

The original store held a hierarchical tree of MemoryNodes at 6 levels.
Replaced with a no-op stub. The system now reads directly from event_log
and frame_buffer for the last 5 minutes.

Imports are preserved so nothing else breaks.
"""

from typing import Literal, Optional

Level = Literal["5min", "10min", "30min", "1hr", "12hr", "daily"]

SPAN: dict[str, float] = {
    "5min":  300,
    "10min": 600,
    "30min": 1800,
    "1hr":   3600,
    "12hr":  43200,
    "daily": 86400,
}


class MemoryNode:
    pass


class MemoryStore:
    def add_node(self, *args, **kwargs) -> Optional[MemoryNode]:
        return None

    def get_nodes_in_range(self, *args, **kwargs) -> list:
        return []

    def get_latest_nodes(self, *args, **kwargs) -> list:
        return []


_store = MemoryStore()


def get_store() -> MemoryStore:
    return _store
