"""Vision tools — capture and return webcam frames for multimodal analysis."""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.services.frame_buffer import get_latest_frame
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
async def capture_webcam(config: RunnableConfig) -> list:
    """Capture the latest frame from the user's webcam.

    Use this tool whenever you need to see what is happening in the user's environment,
    identify objects, describe a scene, or answer any question that requires visual context
    not already present in the conversation history.

    This tool returns the image data which you will then be able to 'see' and analyze.
    """
    from src.tools.progress import emit_progress

    emit_progress("Looking through the camera…")
    thread_id = config.get("configurable", {}).get("thread_id", "default")

    b64_frame = await get_latest_frame(thread_id)
    if not b64_frame:
        return [
            {"type": "text", "text": "No camera frame available. Make sure the camera is enabled and streaming."}
        ]

    logger.info("capture_webcam: frame retrieved for thread=%s", thread_id)

    # Return as a multimodal content block for the llama.cpp / OpenAI-compatible model
    return [
        {"type": "text", "text": "Frame captured successfully."},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64_frame}"}
        }
    ]
