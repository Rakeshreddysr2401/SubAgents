"""Audio tools — provide the agent with a voice on the Mac."""

import subprocess
from langchain_core.tools import tool
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

def speak_out_loud(text: str) -> None:
    """Speak the provided text out loud using the Mac's system voice.
    
    This is now a utility function called by the backend.
    """
    try:
        logger.info(f"Speaking: {text[:50]}...")
        subprocess.run(["say", text], check=False)
    except Exception as e:
        logger.error(f"Speech failed: {e}")
