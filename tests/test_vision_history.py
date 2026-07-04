"""Vision-frame indexing in the post-turn pipeline."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


@pytest.fixture
def capture_indexed(monkeypatch):
    """Capture what index_vision_frames upserts, without touching Qdrant."""
    import src.memory.history_index as hi

    calls = []

    async def _fake_upsert(collection, texts, payloads):
        calls.append((collection, texts, payloads))
        return ["id"]

    monkeypatch.setattr(hi, "upsert_texts", _fake_upsert)
    return calls


async def test_frame_indexed_when_camera_used(capture_indexed, monkeypatch):
    monkeypatch.setenv("VISION_INDEXING", "reuse")
    from src.configs.settings import get_settings

    get_settings.cache_clear()

    from src.memory.history_index import index_vision_frames

    messages = [
        HumanMessage(content="what am I holding?"),
        ToolMessage(content="Frame captured.", name="capture_webcam", tool_call_id="c1"),
        AIMessage(content="You are holding a red coffee mug."),
    ]
    await index_vision_frames(None, "t1", "u1", messages, "what am I holding?")

    assert capture_indexed, "a frame entry should have been indexed"
    collection, texts, payloads = capture_indexed[0]
    assert "red coffee mug" in texts[0]
    assert payloads[0]["kind"] == "frame"
    get_settings.cache_clear()


async def test_no_frame_indexed_without_camera(capture_indexed, monkeypatch):
    monkeypatch.setenv("VISION_INDEXING", "reuse")
    from src.configs.settings import get_settings

    get_settings.cache_clear()

    from src.memory.history_index import index_vision_frames

    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="Hello!"),
    ]
    await index_vision_frames(None, "t1", "u1", messages, "hi")
    assert not capture_indexed
    get_settings.cache_clear()


async def test_vision_indexing_off(capture_indexed, monkeypatch):
    monkeypatch.setenv("VISION_INDEXING", "off")
    from src.configs.settings import get_settings

    get_settings.cache_clear()

    from src.memory.history_index import index_vision_frames

    messages = [
        HumanMessage(content="what is this?"),
        ToolMessage(content="Frame captured.", name="capture_webcam", tool_call_id="c1"),
        AIMessage(content="A book."),
    ]
    await index_vision_frames(None, "t1", "u1", messages, "what is this?")
    assert not capture_indexed
    get_settings.cache_clear()
