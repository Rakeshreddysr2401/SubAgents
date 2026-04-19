from langchain_core.tools import tool
from src.core.world_model import get_world_model

@tool
def recall_world() -> str:
    """Returns the current structured scene: who is present, visible objects, 
    ongoing activity, and environment type. Use this for 'right now' questions.
    """
    return get_world_model().get_current_state()
