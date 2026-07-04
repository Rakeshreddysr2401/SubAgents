"""recall_memories — parent-graph node that injects Mem0 memories per turn.

Runs once before the swarm. Searches Mem0 for memories relevant to the latest
user message (scoped by user_id from the run config) and writes them into
`recalled_memories`, which the agent prompts surface as
"## What you remember about this user".
"""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.api.auth import DEFAULT_USER
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings

logger = get_logger(__name__)


def _last_user_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content if isinstance(msg.content, str) else ""
    return ""


def make_recall_node(mem0):
    """Build the recall node bound to a Mem0 instance (or None to disable)."""

    async def recall_memories(state: dict, config: RunnableConfig) -> dict:
        if mem0 is None:
            return {}
        query = _last_user_text(state.get("messages", []))
        if not query:
            return {}
        user_id = (config.get("configurable") or {}).get("user_id", DEFAULT_USER)
        try:
            result = await mem0.search(
                query,
                filters={"user_id": user_id},
                top_k=get_settings().recall_limit,
            )
            items = result.get("results", []) if isinstance(result, dict) else result
            memories = [it["memory"] for it in items if it.get("memory")]
        except Exception as e:
            logger.warning("Mem0 recall failed: %s", e)
            return {}
        if memories:
            logger.info("Recalled %d memories for user=%s", len(memories), user_id)
        return {"recalled_memories": memories}

    return recall_memories
