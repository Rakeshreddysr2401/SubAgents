"""Hierarchical memory tree for perceptual agent.

Stores summaries at multiple time granularities:
  raw (event captions) → 5min → 10min → 30min → 1hr → 12hr → daily

Each MemoryNode knows its parent and children, enabling drill-down queries:
  - Start at coarsest matching level
  - Drill into children until answer is sufficient
  - Fall through to raw frames (CLIP) if text is insufficient
"""

import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal, Optional

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

Level = Literal["5min", "10min", "30min", "1hr", "12hr", "daily"]

# How long (seconds) each level's nodes are retained
RETENTION: dict[str, float] = {
    "5min":  3 * 3600,       # 3 hours
    "10min": 6 * 3600,       # 6 hours
    "30min": 12 * 3600,      # 12 hours
    "1hr":   48 * 3600,      # 2 days
    "12hr":  14 * 24 * 3600, # 2 weeks
    "daily": float("inf"),   # indefinite
}

# Duration (seconds) each level covers
SPAN: dict[str, float] = {
    "5min":  5 * 60,
    "10min": 10 * 60,
    "30min": 30 * 60,
    "1hr":   3600,
    "12hr":  12 * 3600,
    "daily": 24 * 3600,
}


@dataclass
class MemoryNode:
    id: str
    level: Level
    start_time: float          # unix timestamp
    end_time: float            # unix timestamp
    summary: str
    thread_id: str
    children_ids: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None


class MemoryStore:
    """Thread-safe in-memory tree of MemoryNodes, one store per thread_id."""

    def __init__(self):
        self._lock = threading.Lock()
        # node_id -> MemoryNode
        self._nodes: dict[str, MemoryNode] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_node(
        self,
        thread_id: str,
        level: Level,
        start_time: float,
        end_time: float,
        summary: str,
        children_ids: list[str] | None = None,
    ) -> MemoryNode:
        """Create and store a new MemoryNode. Links parent pointers on children."""
        node = MemoryNode(
            id=str(uuid.uuid4()),
            level=level,
            start_time=start_time,
            end_time=end_time,
            summary=summary,
            thread_id=thread_id,
            children_ids=children_ids or [],
        )
        with self._lock:
            self._nodes[node.id] = node
            # Point each child's parent_id to this new node
            for cid in node.children_ids:
                if cid in self._nodes:
                    self._nodes[cid].parent_id = node.id

        logger.debug("MemoryStore: added %s node %s [%.0f–%.0f]", level, node.id, start_time, end_time)
        return node

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def get_children(self, node_id: str) -> list[MemoryNode]:
        """Return child nodes ordered by start_time."""
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return []
            children = [self._nodes[cid] for cid in node.children_ids if cid in self._nodes]
        return sorted(children, key=lambda n: n.start_time)

    def get_nodes_in_range(
        self,
        thread_id: str,
        level: Level,
        start: float,
        end: float,
    ) -> list[MemoryNode]:
        """Return all nodes at a given level that overlap [start, end], ordered by start_time."""
        with self._lock:
            results = [
                n for n in self._nodes.values()
                if n.thread_id == thread_id
                and n.level == level
                and n.start_time < end
                and n.end_time > start
            ]
        return sorted(results, key=lambda n: n.start_time)

    def get_latest_nodes(self, thread_id: str, level: Level, count: int = 1) -> list[MemoryNode]:
        """Return the most recent `count` nodes at a given level."""
        with self._lock:
            nodes = [
                n for n in self._nodes.values()
                if n.thread_id == thread_id and n.level == level
            ]
        return sorted(nodes, key=lambda n: n.start_time)[-count:]

    def get_all_levels(self, thread_id: str) -> dict[Level, list[MemoryNode]]:
        """Return all nodes grouped by level, for a thread."""
        with self._lock:
            all_nodes = [n for n in self._nodes.values() if n.thread_id == thread_id]
        result: dict[Level, list[MemoryNode]] = {}
        for node in all_nodes:
            result.setdefault(node.level, []).append(node)
        for level in result:
            result[level].sort(key=lambda n: n.start_time)
        return result

    # ------------------------------------------------------------------
    # Drill-down
    # ------------------------------------------------------------------

    def drill_down(self, node_id: str) -> list[MemoryNode]:
        """Return immediate children of a node (one level finer granularity)."""
        return self.get_children(node_id)

    def drill_down_full(self, node_id: str) -> list[MemoryNode]:
        """Recursively return ALL descendants of a node (leaf = 5min nodes)."""
        children = self.get_children(node_id)
        if not children:
            return []
        result = list(children)
        for child in children:
            result.extend(self.drill_down_full(child.id))
        return sorted(result, key=lambda n: n.start_time)

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def evict_expired(self) -> int:
        """Remove nodes older than their retention window. Returns count removed."""
        import time
        now = time.time()
        to_remove = []
        with self._lock:
            for node_id, node in self._nodes.items():
                retention = RETENTION.get(node.level, float("inf"))
                if retention != float("inf") and now - node.end_time > retention:
                    to_remove.append(node_id)
            for node_id in to_remove:
                del self._nodes[node_id]
        if to_remove:
            logger.debug("MemoryStore: evicted %d expired nodes", len(to_remove))
        return len(to_remove)


# ---------------------------------------------------------------------------
# Module-level singleton store (shared across all thread_ids)
# ---------------------------------------------------------------------------
_store = MemoryStore()


def get_store() -> MemoryStore:
    return _store
