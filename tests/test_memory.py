"""Recall node + post-turn pipeline with a stub Mem0."""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage


class StubMem0:
    def __init__(self, search_results=None):
        self._search_results = search_results or []
        self.added = []

    async def add(self, messages, user_id=None, **kwargs):
        self.added.append((messages, user_id))
        return {"results": []}

    async def search(self, query, filters=None, top_k=5, **kwargs):
        return {"results": self._search_results}


async def test_recall_injects_memories():
    from src.memory.recall import make_recall_node

    mem0 = StubMem0(search_results=[{"memory": "User is vegetarian"}, {"memory": "Allergic to peanuts"}])
    node = make_recall_node(mem0)
    state = {"messages": [HumanMessage(content="what should I eat?")]}
    config = {"configurable": {"user_id": "u1"}}
    out = await node(state, config)
    assert out["recalled_memories"] == ["User is vegetarian", "Allergic to peanuts"]


async def test_recall_disabled_when_no_mem0():
    from src.memory.recall import make_recall_node

    node = make_recall_node(None)
    out = await node({"messages": [HumanMessage(content="hi")]}, {"configurable": {}})
    assert out == {}


async def test_post_turn_writes_last_exchange(monkeypatch):
    from src.memory import post_turn

    mem0 = StubMem0()
    messages = [
        HumanMessage(content="I love spicy food"),
        AIMessage(content="Noted — I'll suggest spicy dishes."),
    ]

    class FakeGraph:
        async def aget_state(self, config):
            return SimpleNamespace(values={"messages": messages})

    app = SimpleNamespace(state=SimpleNamespace(graph=FakeGraph(), mem0=mem0))

    # Stub the history/vision indexing (real path hits the utility LLM + Qdrant)
    import src.memory.history_index as hi

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(hi, "index_turn", _noop)
    monkeypatch.setattr(hi, "index_vision_frames", _noop)

    await post_turn.run_post_turn(app, "t1", "u1")

    assert len(mem0.added) == 1
    msgs, user_id = mem0.added[0]
    assert user_id == "u1"
    assert msgs[0]["content"] == "I love spicy food"
    assert "spicy dishes" in msgs[1]["content"]
