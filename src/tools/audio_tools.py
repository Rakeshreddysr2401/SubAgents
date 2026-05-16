"""Audio tools — provide the agent with a voice on the Mac."""

import asyncio
from langchain_core.tools import tool
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
async def speak_out_loud(text: str) -> str:
    """Speak the provided text out loud using the Mac's system voice.
    
    Use this when you want to provide a verbal response or confirmation to the user.
    """
    try:
        logger.info(f"Speaking: {text[:50]}...")
        proc = await asyncio.create_subprocess_exec(
            "say", text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return "Spoken successfully."
    except Exception as e:
        logger.error(f"Speech failed: {e}")
        return f"Speech failed: {e}"
