from langgraph.checkpoint.memory import MemorySaver

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

#Need to Add Redis / Postgres For Production
def get_memory() -> MemorySaver:
    """Return a memory checkpointer."""
    logger.info("Using MemorySaver (in-memory checkpointer)")
    return MemorySaver()


