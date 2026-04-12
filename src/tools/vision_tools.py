"""Vision tools — real-time camera frame analysis via LLaVA."""

import os
import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.utils.frame_buffer import get_latest_frames
from src.llm_config import OLLAMA_BASE_URL
from src.configs.logging_config import get_logger

# Import the semaphore from perception_loop so look_now and background captions
# never call LLaVA at the same time (they share one Ollama instance).
from src.utils.perception_loop import _caption_semaphore

logger = get_logger(__name__)

OLLAMA_VISION_MODEL = "llava"
_VISION_URL = os.getenv("OLLAMA_VISION_URL", OLLAMA_BASE_URL)


@tool
def look_now(query: str, config: RunnableConfig) -> str:
    """Take a fresh camera frame right now and answer a specific visual question.

    Use this when you need current real-time detail that the text log cannot provide:
    - "what am I doing right now?"
    - "what color is my shirt / bag / item?"
    - "how many people are in the room?"
    - "describe what you see right now"
    - "is there anything on the desk?"
    - any question about specific visual details or the current state of the scene

    Do NOT use this if recall_recent already has the answer in its text log —
    this tool calls the vision model and takes time.

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

    logger.info("look_now: waiting for LLaVA slot (query=%s)", query[:60])

    # Wait for the LLaVA semaphore — user requests always go through,
    # but we wait if a background caption is currently running.
    _caption_semaphore.acquire()
    try:
        logger.info("look_now: sending frame to LLaVA")
        resp = requests.post(
            f"{_VISION_URL}/api/generate",
            json={
                "model": OLLAMA_VISION_MODEL,
                "prompt": query,
                "images": [frames[-1]],
                "stream": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
        if not answer:
            return "Vision model returned no response."
        return answer

    except requests.ConnectionError:
        return (
            f"Vision service (Ollama/LLaVA) is not reachable at {_VISION_URL}. "
            "Make sure Ollama is running with: ollama serve"
        )
    except requests.Timeout:
        return (
            "Vision service timed out (60s). LLaVA may still be loading. "
            "Try again in a moment."
        )
    except Exception as e:
        logger.exception("look_now error: %s", e)
        return f"Visual analysis failed: {e}"
    finally:
        _caption_semaphore.release()
