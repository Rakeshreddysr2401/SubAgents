"""Critical swarm-routing suite.

Uses a scripted fake tool-calling model injected via the get_llm seam,
MemorySaver for persistence, and no external services.
"""

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from pydantic import Field

from src.commons.constants import CONVERSATION, SWIGGY


class FakeToolCallingModel(BaseChatModel):
    """Pops one scripted response per LLM call; records the prompts it saw."""

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
    """Build the swarm graph with a scripted fake model and MemorySaver."""

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


async def test_default_agent_answers(make_graph):
    graph, fake = make_graph([AIMessage(content="Hi there!")])
    result = await graph.ainvoke(_inputs("hello"), CFG)
    assert result["messages"][-1].content == "Hi there!"
    # One LLM call, made by the conversation agent (its system prompt)
    assert len(fake.calls) == 1
    assert "default router" in fake.calls[0][0].content


async def test_handoff_chains_same_turn(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "user wants dosa"}),
            AIMessage(content="Here are some dosa options."),
        ]
    )
    result = await graph.ainvoke(_inputs("order me a dosa"), CFG)
    assert result["active_agent"] == SWIGGY
    assert result["messages"][-1].content == "Here are some dosa options."
    # Second call went to the swiggy agent and saw the bridge message
    assert "Swiggy food ordering assistant" in fake.calls[1][0].content
    bridge_texts = [
        m.content for m in fake.calls[1] if "You are now the swiggy agent" in str(m.content)
    ]
    assert bridge_texts, "swiggy should see the handoff bridge with the reason"
    assert "user wants dosa" in bridge_texts[0]


async def test_sticky_follow_up_goes_straight_to_active_agent(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "food order"}),
            AIMessage(content="Options ready."),
            AIMessage(content="Sure — extra spicy noted."),
        ]
    )
    await graph.ainvoke(_inputs("order dosa"), CFG)
    result = await graph.ainvoke(_inputs("make it extra spicy"), CFG)
    assert result["active_agent"] == SWIGGY
    assert result["messages"][-1].content == "Sure — extra spicy noted."
    # Turn 2 = exactly one LLM call, by swiggy directly (sticky routing)
    assert len(fake.calls) == 3
    assert "Swiggy food ordering assistant" in fake.calls[2][0].content


async def test_loop_guard_refuses_handoff(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "again"}),
            AIMessage(content="Answering directly instead."),
        ]
    )
    inputs = {
        "messages": [HumanMessage(content="order dosa")],
        "agent_turn_visits": {SWIGGY: 3},  # already at the limit
    }
    result = await graph.ainvoke(inputs, CFG)
    # Handoff was refused: conversation answered itself, control never moved
    assert result["messages"][-1].content == "Answering directly instead."
    assert result.get("active_agent") != SWIGGY
    refusals = [
        m
        for m in result["messages"]
        if isinstance(m, ToolMessage) and "Handoff refused" in str(m.content)
    ]
    assert refusals, "expected a refusal ToolMessage"
    # Both calls made by conversation agent
    assert "default router" in fake.calls[1][0].content


async def test_agent_turn_visits_resets_per_turn(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "food"}),
            AIMessage(content="Options."),
            _tool_call("transfer_to_conversation", {"reason": "weather question"}),
            AIMessage(content="It's sunny."),
        ]
    )
    r1 = await graph.ainvoke(_inputs("order dosa"), CFG)
    assert r1["agent_turn_visits"] == {SWIGGY: 1}
    # New turn passes a fresh {} which overwrites the counter
    r2 = await graph.ainvoke(_inputs("what's the weather?"), CFG)
    assert r2["agent_turn_visits"] == {CONVERSATION: 1}
    assert r2["active_agent"] == CONVERSATION
    assert r2["messages"][-1].content == "It's sunny."


async def test_stale_bridge_messages_are_pruned(make_graph):
    graph, fake = make_graph(
        [
            _tool_call("transfer_to_swiggy", {"reason": "food"}),
            AIMessage(content="Options."),
            _tool_call("transfer_to_conversation", {"reason": "off-topic"}),
            AIMessage(content="42."),
        ]
    )
    await graph.ainvoke(_inputs("order dosa"), CFG)
    await graph.ainvoke(_inputs("meaning of life?"), CFG)
    # Final call (conversation agent) must see at most ONE bridge SystemMessage
    from langchain_core.messages import SystemMessage

    last_prompt = fake.calls[-1]
    bridges = [
        m
        for m in last_prompt[1:]  # skip the agent's own system prompt at index 0
        # The trailing live-clock SystemMessage (LiveClockMiddleware) is not a bridge.
        if isinstance(m, SystemMessage) and "Current date & time" not in m.content
    ]
    assert len(bridges) <= 1
    if bridges:
        assert "You are now the conversation agent" in bridges[0].content
