"""Vision tools — real-time camera frame analysis via llama.cpp (Gemma multimodal)."""

import os
import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.utils.frame_buffer import get_latest_frames
from src.llm_config import VISION_BASE_URL, VISION_MODEL_NAME
from src.configs.logging_config import get_logger
from src.utils.perception_loop import _caption_semaphore

logger = get_logger(__name__)

# Allow overriding vision endpoint independently (e.g. separate GPU machine).
_VISION_URL = os.getenv("VISION_BASE_URL", VISION_BASE_URL)


def _call_vision(query: str, b64_jpeg: str, timeout: int = 120) -> str:
    """POST a base64 JPEG + query to the llama.cpp OpenAI-compatible endpoint."""
    resp = requests.post(
        f"{_VISION_URL}/chat/completions",
        headers={"Authorization": "Bearer not-needed", "Content-Type": "application/json"},
        json={
            "model": VISION_MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_jpeg}"},
                        },
                    ],
                }
            ],
            "max_tokens": 300,
            "stream": False,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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

    logger.info("look_now: waiting for vision slot (query=%s)", query[:60])

    # Block until background caption finishes — user queries always go through.
    _caption_semaphore.acquire()
    try:
        logger.info("look_now: sending frame to Gemma vision")
        answer = _call_vision(query, frames[-1], timeout=120)
        return answer or "Vision model returned no response."

    except requests.ConnectionError:
        return (
            f"Vision service (llama.cpp) is not reachable at {_VISION_URL}. "
            "Make sure llama-server is running: llama-server --mmproj ..."
        )
    except requests.Timeout:
        return (
            "Vision service timed out. Gemma may still be loading. "
            "Try again in a moment."
        )
    except Exception as e:
        logger.exception("look_now error: %s", e)
        return f"Visual analysis failed: {e}"
    finally:
        _caption_semaphore.release()
