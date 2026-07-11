"""Routing for the instamart/dineout agents + the provider-unavailable prompt swap.

Mirrors tests/test_graph_routing.py's scripted-fake-model pattern.
"""

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from src.commons.constants import DINEOUT, INSTAMART
from src.services import mcp_providers as mcp


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


@pytest.fixture(autouse=True)
def fresh_mcp_state():
    mcp.reset_state()
    yield
    mcp.reset_state()


@pytest.fixture
def make_graph(monkeypatch):
    def _make(responses: list):
        fake = FakeToolCallingModel(responses=list(responses))
        import src.graph.swarm as swarm_mod

        monkeypatch.setattr(swarm_mod, "get_llm", lambda temperature=0: fake)
        from src.graph.build import build_graph

        return build_graph(checkpointer=MemorySaver()), fake

    return _make


CFG = {"configurable": {"thread_id": "t1"}}


def _inputs(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)], "agent_turn_visits": {}}


async def test_handoff_to_instamart(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_instamart", {"reason": "grocery order"}),
            AIMessage(content="Groceries coming up."),
        ]
    )
    result = await graph.ainvoke(_inputs("order milk and eggs"), CFG)
    assert result["active_agent"] == INSTAMART
    assert result["messages"][-1].content == "Groceries coming up."
    assert "Instamart grocery shopping assistant" in fake.calls[1][0].content


async def test_handoff_to_dineout(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_dineout", {"reason": "table for two"}),
            AIMessage(content="Table options found."),
        ]
    )
    result = await graph.ainvoke(_inputs("book a table for 2 tonight"), CFG)
    assert result["active_agent"] == DINEOUT
    assert result["messages"][-1].content == "Table options found."
    assert "Dineout table reservation assistant" in fake.calls[1][0].content


async def test_unavailable_note_appended_when_provider_down(make_graph):
    """Fresh state = no token, no tools → the swiggy agent's prompt carries
    the not_connected note (stops tool-loop flailing) and never tells the
    user to 'try again later'."""
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "dosa"}),
            AIMessage(content="Let's get your Swiggy connected first."),
        ]
    )
    await graph.ainvoke(_inputs("order dosa"), CFG)
    swiggy_prompt = fake.calls[1][0].content
    assert "not connected yet" in swiggy_prompt
    assert "Settings → Integrations" in swiggy_prompt
    # It instructs the model NOT to stall the user with "try again later".
    assert 'do not say "try again later"' in swiggy_prompt


async def test_unavailable_note_absent_when_provider_ok(make_graph, monkeypatch):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "dosa"}),
            AIMessage(content="Here are options."),
        ]
    )
    monkeypatch.setattr("src.services.mcp_providers.provider_unavailable_reason", lambda name: None)
    await graph.ainvoke(_inputs("order dosa"), CFG)
    swiggy_prompt = fake.calls[1][0].content
    assert "not connected yet" not in swiggy_prompt


async def test_instamart_to_tracker_after_order(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_instamart", {"reason": "groceries"}),
            _tool_call("transfer_to_tracker", {"reason": "order_placed"}, call_id="call_2"),
            AIMessage(content="Your groceries arrive in 12 minutes."),
        ]
    )
    result = await graph.ainvoke(_inputs("order milk"), CFG)
    assert result["active_agent"] == "tracker"
    assert result["messages"][-1].content == "Your groceries arrive in 12 minutes."
    assert "order tracking assistant" in fake.calls[2][0].content
