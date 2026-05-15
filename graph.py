from src.agents.supervisor_agent import  builder
from src.configs.memory_config import get_memory

graph = builder.compile(checkpointer=get_memory())
__all__ = ["graph"]