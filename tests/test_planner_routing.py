"""Planner (real deepagents) routing suite.

Mirrors test_graph_routing.py's FakeToolCallingModel + MemorySaver pattern.
Confirms the planner composes into the swarm as a normal peer: reachable via
transfer_to_planner from any agent, and able to delegate onward via its own
transfer_to_* tools.
"""

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from src.commons.constants import PLANNER, SWIGGY


class FakeToolCallingModel(BaseChatModel):
    responses: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeToolCallingModel ran out of scripted responses")
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])

    def bind_tools(self, tools, **kwargs) -> "FakeToolCallingModel":
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"


def _tool_call(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture
def make_graph(monkeypatch):
    def _make(responses: list):
        fake = FakeToolCallingModel(responses=list(responses))
        import src.graph.swarm as swarm_mod

        monkeypatch.setattr(swarm_mod, "get_llm", lambda temperature=0: fake)
        from src.graph.build import build_graph

        return build_graph(checkpointer=MemorySaver()), fake

    return _make


CFG = {"configurable": {"thread_id": "planner-t1"}}


def _inputs(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)], "agent_turn_visits": {}}


async def test_conversation_transfers_to_planner_for_multistep_request(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_planner", {"reason": "multi-step: find, order, track"}),
            AIMessage(content="Plan: 1) find a dosa place 2) order 3) track."),
        ]
    )
    result = await graph.ainvoke(
        _inputs("find me a dosa place, order from it, then track it"), CFG
    )
    assert result["active_agent"] == PLANNER
    assert result["messages"][-1].content == "Plan: 1) find a dosa place 2) order 3) track."


async def test_planner_delegates_onward_to_swiggy(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_planner", {"reason": "multi-step order+track"}),
            _tool_call("transfer_to_swiggy", {"reason": "step 1: order dosa"}),
            AIMessage(content="Found a place and placed the order."),
        ]
    )
    result = await graph.ainvoke(_inputs("order a dosa then track it"), CFG)
    assert result["active_agent"] == SWIGGY
    assert result["messages"][-1].content == "Found a place and placed the order."
    # Bridge from planner should mention the delegated reason
    bridge_texts = [
        m.content for m in fake.calls[-1] if "You are now the swiggy agent" in str(m.content)
    ]
    assert bridge_texts, "swiggy should see the handoff bridge from the planner"
