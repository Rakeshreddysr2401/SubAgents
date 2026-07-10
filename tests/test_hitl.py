"""Human-in-the-loop approval suite.

Mirrors test_graph_routing.py's FakeToolCallingModel + MemorySaver pattern.
Uses the real `open_mac_app` tool (gated via GATED_TOOL_NAMES) but patches
`subprocess.run` so approve/edit paths never actually shell out on the test
runner.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import Field

from src.commons.constants import CONVERSATION


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
    """Build the real swarm graph (with HITL middleware wired in) + fake model."""

    fake_subprocess_run = MagicMock()
    monkeypatch.setattr("src.tools.system_tools.subprocess.run", fake_subprocess_run)

    def _make(responses: list):
        fake = FakeToolCallingModel(responses=list(responses))
        import src.graph.swarm as swarm_mod

        monkeypatch.setattr(swarm_mod, "get_llm", lambda temperature=0: fake)
        from src.graph.build import build_graph

        return build_graph(checkpointer=MemorySaver()), fake, fake_subprocess_run

    return _make


def _inputs(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)], "agent_turn_visits": {}}


async def test_gated_tool_call_interrupts(make_graph):
    graph, fake, subprocess_run = make_graph(
        [_tool_call("open_mac_app", {"app_name": "Safari"}), AIMessage(content="Done.")]
    )
    cfg = {"configurable": {"thread_id": "hitl-interrupt"}}
    result = await graph.ainvoke(_inputs("open safari"), cfg)
    assert "__interrupt__" in result
    interrupt = result["__interrupt__"][0]
    assert interrupt.value["action_requests"][0]["name"] == "open_mac_app"
    assert interrupt.value["action_requests"][0]["args"] == {"app_name": "Safari"}
    # Paused before execution — the real tool must not have run yet.
    subprocess_run.assert_not_called()


async def test_approve_runs_the_tool(make_graph):
    graph, fake, subprocess_run = make_graph(
        [_tool_call("open_mac_app", {"app_name": "Safari"}), AIMessage(content="Done.")]
    )
    cfg = {"configurable": {"thread_id": "hitl-approve"}}
    await graph.ainvoke(_inputs("open safari"), cfg)
    result = await graph.ainvoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg)

    subprocess_run.assert_called_once_with(["open", "-a", "Safari"], check=True)
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages and "Successfully opened Safari" in tool_messages[0].content
    assert result["messages"][-1].content == "Done."


async def test_reject_skips_the_tool(make_graph):
    graph, fake, subprocess_run = make_graph(
        [_tool_call("open_mac_app", {"app_name": "Safari"}), AIMessage(content="Okay, skipped.")]
    )
    cfg = {"configurable": {"thread_id": "hitl-reject"}}
    await graph.ainvoke(_inputs("open safari"), cfg)
    result = await graph.ainvoke(
        Command(resume={"decisions": [{"type": "reject", "message": "Not right now."}]}), cfg
    )

    subprocess_run.assert_not_called()
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages and tool_messages[0].content == "Not right now."
    assert result["messages"][-1].content == "Okay, skipped."


async def test_edit_changes_the_args_before_running(make_graph):
    graph, fake, subprocess_run = make_graph(
        [_tool_call("open_mac_app", {"app_name": "Safari"}), AIMessage(content="Opened Notes instead.")]
    )
    cfg = {"configurable": {"thread_id": "hitl-edit"}}
    await graph.ainvoke(_inputs("open safari"), cfg)
    result = await graph.ainvoke(
        Command(
            resume={
                "decisions": [
                    {"type": "edit", "edited_action": {"name": "open_mac_app", "args": {"app_name": "Notes"}}}
                ]
            }
        ),
        cfg,
    )

    subprocess_run.assert_called_once_with(["open", "-a", "Notes"], check=True)
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages and "Successfully opened Notes" in tool_messages[0].content


async def test_ungated_tool_does_not_interrupt(make_graph):
    """get_system_info isn't in GATED_TOOL_NAMES — should run without pausing."""
    graph, fake, subprocess_run = make_graph(
        [_tool_call("get_system_info", {}), AIMessage(content="It's currently daytime.")]
    )
    cfg = {"configurable": {"thread_id": "hitl-ungated"}}
    result = await graph.ainvoke(_inputs("what time is it"), cfg)
    assert "__interrupt__" not in result
    assert result["messages"][-1].content == "It's currently daytime."
    assert result.get("active_agent", CONVERSATION) == CONVERSATION


async def test_ask_user_choice_interrupts_and_respond_returns_selection(make_graph):
    """ask_user_choice rides the same interrupt rails: the {question, options}
    args reach the browser typed, and the "respond" decision comes back to
    the model as the tool's result (the user's selection)."""
    graph, fake, subprocess_run = make_graph(
        [
            _tool_call("ask_user_choice", {
                "question": "Which delivery address should I use?",
                "options": ["Home — 12 MG Road", "Office — Tower B"],
            }),
            AIMessage(content="Delivering to the office."),
        ]
    )
    cfg = {"configurable": {"thread_id": "hitl-choice"}}
    result = await graph.ainvoke(_inputs("order a dosa to my usual place"), cfg)

    interrupt = result["__interrupt__"][0]
    request = interrupt.value["action_requests"][0]
    assert request["name"] == "ask_user_choice"
    assert request["args"]["options"] == ["Home — 12 MG Road", "Office — Tower B"]
    # The gate restricts decisions to respond/reject — no blind "approve".
    review = interrupt.value["review_configs"][0]
    assert set(review["allowed_decisions"]) == {"respond", "reject"}

    result = await graph.ainvoke(
        Command(resume={"decisions": [{"type": "respond", "message": "Office — Tower B"}]}),
        cfg,
    )
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages and "Office — Tower B" in tool_messages[-1].content
    assert result["messages"][-1].content == "Delivering to the office."
