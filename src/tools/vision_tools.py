"""Vision tools — real-time camera frame analysis via LLaVA."""

import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.utils.frame_buffer import get_latest_frames
from src.llm_config import OLLAMA_BASE_URL
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

OLLAMA_VISION_MODEL = "llava"


@tool
def look_now(query: str, config: RunnableConfig) -> str:
    """Take a fresh camera frame and answer a specific visual question right now.

    Use this when you need current real-time detail that the text log cannot provide:
    - "what am I doing right now?"
    - "what color is my shirt / bag / item?"
    - "how many people are in the room?"
    - "describe what you see right now"
    - "is there anything on the desk?"
    - any question about specific visual details or the current state of the scene

    Do NOT use this if recall_recent already has the answer in its text log —
    this tool calls the vision model and is slower.

    Args:
        query: Your specific question about what the camera currently sees.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    frames = get_latest_frames(thread_id, count=1)
    if not frames:
        return (
            "No camera frame available. "
            "Make sure the camera is enabled and streaming."
        )

    logger.info("look_now: sending frame to LLaVA for query=%s", query[:80])

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": query,
                "images": [frames[-1]],
                "stream": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        if not answer:
            return "Vision model returned no response."
        return answer

    except requests.ConnectionError:
        return (
            f"Vision service (Ollama/LLaVA) is not reachable at {OLLAMA_BASE_URL}. "
            "Make sure Ollama is running."
        )
    except requests.Timeout:
        return "Vision service timed out. LLaVA may still be loading — try again in a moment."
    except Exception as e:
        logger.exception("look_now error: %s", e)
        return f"Visual analysis failed: {e}"
