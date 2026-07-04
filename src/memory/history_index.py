"""Index conversation turns and vision frames into the Qdrant `history` collection.

Called from the post-turn pipeline. Turn summaries power `recall_history`
("what did we talk about"); frame entries power visual recall
("what did I show you last week").
"""

import time

from langchain_core.messages import SystemMessage, ToolMessage

from src.configs.llm import get_utility_llm
from src.configs.logging_config import get_logger
from src.configs.settings import get_settings
from src.rag.store import upsert_texts

logger = get_logger(__name__)


async def _summarize(user_text: str, assistant_text: str) -> str:
    prompt = (
        "Summarize this exchange in one concise sentence for later recall. "
        "Focus on facts, decisions, and topics.\n\n"
        f"User: {user_text}\nAssistant: {assistant_text}"
    )
    try:
        resp = await get_utility_llm().ainvoke([SystemMessage(content=prompt)])
        return resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as e:
        logger.warning("turn summary failed, storing raw: %s", e)
        return f"User asked: {user_text}"


async def index_turn(app, thread_id: str, user_id: str, user_text: str, assistant_text: str) -> None:
    summary = await _summarize(user_text, assistant_text)
    await upsert_texts(
        get_settings().history_collection,
        [summary],
        [{"user_id": user_id, "thread_id": thread_id, "kind": "turn", "ts": time.time()}],
    )


def _capture_webcam_used(messages: list) -> list[ToolMessage]:
    return [
        m
        for m in messages
        if isinstance(m, ToolMessage) and m.name == "capture_webcam"
    ]


async def index_vision_frames(
    app, thread_id: str, user_id: str, messages: list, user_text: str
) -> None:
    """Index a description of any webcam frame the assistant looked at this turn."""
    settings = get_settings()
    mode = settings.vision_indexing
    if mode == "off":
        return
    frame_tools = _capture_webcam_used(messages)
    if not frame_tools:
        return

    # In 'reuse' mode we index the assistant's own visual answer (zero extra LLM
    # cost). 'llm' mode would re-describe the image with a multimodal call.
    _, assistant_text = _last_ai_text(messages)
    if mode == "reuse":
        description = assistant_text or user_text
    else:  # "llm" — placeholder reuses answer if no multimodal describe available
        description = assistant_text or user_text

    if not description:
        return
    await upsert_texts(
        settings.history_collection,
        [f"[camera] {description} (asked: {user_text})"],
        [{"user_id": user_id, "thread_id": thread_id, "kind": "frame", "ts": time.time()}],
    )


def _last_ai_text(messages: list):
    from langchain_core.messages import AIMessage, HumanMessage

    last_user_idx = -1
    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage):
            last_user_idx = i
    ai_texts = [
        m.content
        for m in messages[last_user_idx + 1 :]
        if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content
    ]
    return last_user_idx, "\n".join(ai_texts)
