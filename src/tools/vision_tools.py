"""Vision tools — send camera frames to Ollama llava for analysis."""

import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.utils.frame_buffer import get_latest_frames
from src.llm_config import OLLAMA_BASE_URL
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

OLLAMA_VISION_MODEL = "llava"


@tool
def describe_camera_view(query: str, config: RunnableConfig) -> str:
    """Describe what is currently visible in the user's camera feed.
    Use this tool when the user asks what you can see, what is in front of
    them, or any question about their camera/video feed.

    Args:
        query: The user's question about what they see (e.g. "what do you see?",
               "how many cars are there?", "describe the scene").
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    frames = get_latest_frames(thread_id, count=1)
    if not frames:
        return (
            "I don't have access to a camera feed right now. "
            "Please make sure your camera is enabled and streaming."
        )

    frame_b64 = frames[-1]
    logger.info("Vision tool: sending frame to %s/%s", OLLAMA_BASE_URL, OLLAMA_VISION_MODEL)

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": query,
                "images": [frame_b64],
                "stream": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        description = resp.json().get("response", "").strip()
        if not description:
            return "I received the image but could not generate a description."
        return description
    except requests.ConnectionError:
        return (
            f"Vision service (Ollama) is not reachable at {OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running."
        )
    except requests.Timeout:
        return "Vision service timed out. The model may still be loading."
    except Exception as e:
        logger.exception("Vision tool error: %s", e)
        return f"Vision analysis failed: {e}"
