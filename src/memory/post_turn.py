"""Post-turn background pipeline.

Runs after the SSE response has been sent, so it never adds user-facing latency:
  1. Write the user↔assistant exchange to Mem0 (durable facts)
  2. (Phase 5) index a turn summary into the Qdrant `history` collection
  3. (Phase 6) index any webcam frame the assistant looked at

Every step is best-effort: failures are logged and swallowed.
"""

from langchain_core.messages import AIMessage, HumanMessage

from src.configs.logging_config import get_logger

logger = get_logger(__name__)


def _last_exchange(messages: list) -> tuple[str, str]:
    """Return (last user text, concatenated assistant text after it)."""
    last_user_idx = -1
    for i, m in enumerate(messages):
        if isinstance(m, HumanMessage):
            last_user_idx = i
    user_text = ""
    if last_user_idx >= 0 and isinstance(messages[last_user_idx].content, str):
        user_text = messages[last_user_idx].content
    ai_texts = [
        m.content
        for m in messages[last_user_idx + 1 :]
        if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content
    ]
    return user_text, "\n".join(ai_texts)


async def run_post_turn(app, thread_id: str, user_id: str) -> None:
    graph = app.state.graph
    mem0 = getattr(app.state, "mem0", None)
    try:
        snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
        messages = snapshot.values.get("messages", []) if snapshot else []
    except Exception as e:
        logger.warning("post_turn: could not load state: %s", e)
        return

    user_text, assistant_text = _last_exchange(messages)
    if not user_text or not assistant_text:
        return

    if mem0 is not None:
        try:
            await mem0.add(
                [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ],
                user_id=user_id,
            )
            logger.info("Mem0: stored exchange for user=%s", user_id)
        except Exception as e:
            logger.warning("Mem0 add failed: %s", e)

    # History (turn summary) + vision-frame indexing.
    from src.memory.history_index import index_turn, index_vision_frames

    try:
        await index_turn(app, thread_id, user_id, user_text, assistant_text)
        await index_vision_frames(app, thread_id, user_id, messages, user_text)
    except Exception as e:
        logger.warning("history/vision indexing failed: %s", e)
