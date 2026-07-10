"""Time travel: checkpoint listing + forking a thread from an old checkpoint."""

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field


class FakeModel(BaseChatModel):
    responses: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if not self.responses:
            raise AssertionError("FakeModel ran out of scripted responses")
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])

    def bind_tools(self, tools, **kwargs) -> "FakeModel":
        return self

    @property
    def _llm_type(self) -> str:
        return "fake"


@pytest.fixture
def graph(monkeypatch):
    fake = FakeModel(responses=[
        AIMessage(content="Answer one."),
        AIMessage(content="Answer two."),
        AIMessage(content="Forked answer."),
    ])
    import src.graph.swarm as swarm_mod

    monkeypatch.setattr(swarm_mod, "get_llm", lambda temperature=0: fake)
    from src.graph.build import build_graph

    return build_graph(checkpointer=MemorySaver())


CFG = {"configurable": {"thread_id": "tt1"}}


def _inputs(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)], "agent_turn_visits": {}}


class _ThreadStoreStub:
    def __init__(self, owner: str):
        self.owner = owner

    async def get(self, tid):
        return SimpleNamespace(id=tid, user_id=self.owner, title="t")


def _request(graph, owner="u1"):
    state = SimpleNamespace(graph=graph, thread_store=_ThreadStoreStub(owner))
    return SimpleNamespace(app=SimpleNamespace(state=state))


async def test_checkpoints_one_per_turn_and_fork(graph):
    from src.api.threads import thread_checkpoints

    await graph.ainvoke(_inputs("first question"), CFG)
    await graph.ainvoke(_inputs("second question"), CFG)

    result = await thread_checkpoints("tt1", _request(graph), user_id="u1")
    checkpoints = result["checkpoints"]
    # Newest first; one entry per turn boundary (2 turns + the empty start).
    assert len(checkpoints) >= 2
    assert checkpoints[0]["num_messages"] >= checkpoints[-1]["num_messages"]
    tip = checkpoints[0]
    assert tip["last_role"] == "ai"
    assert tip["last_preview"] == "Answer two."

    # Fork: rewind to the boundary after turn 1 and re-ask.
    after_turn_one = next(c for c in checkpoints if c["last_preview"] == "Answer one.")
    fork_cfg = {
        "configurable": {"thread_id": "tt1", "checkpoint_id": after_turn_one["checkpoint_id"]}
    }
    forked = await graph.ainvoke(_inputs("second question, edited"), fork_cfg)
    contents = [m.content for m in forked["messages"]]
    assert "Forked answer." in contents
    assert "Answer one." in contents          # shared history preserved
    assert "Answer two." not in contents      # the replaced branch is gone

    # The original branch is still readable at the thread tip? No — the fork
    # becomes the new tip, but both checkpoints remain in history.
    history = await thread_checkpoints("tt1", _request(graph), user_id="u1")
    previews = [c["last_preview"] for c in history["checkpoints"]]
    assert "Forked answer." in previews


async def test_checkpoints_404_for_wrong_owner(graph):
    from fastapi import HTTPException

    from src.api.threads import thread_checkpoints

    await graph.ainvoke(_inputs("hello"), CFG)
    with pytest.raises(HTTPException) as exc:
        await thread_checkpoints("tt1", _request(graph, owner="someone-else"), user_id="u1")
    assert exc.value.status_code == 404
