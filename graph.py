from typing import TypedDict, List, Optional, Literal
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from dotenv import load_dotenv
import os

# -----------------------------
# ENV
# -----------------------------
load_dotenv()

# -----------------------------
# LLM
# -----------------------------
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=os.getenv("OPENAI_API_KEY")
)

# -----------------------------
# STATE
# -----------------------------
class AgentState(TypedDict):
    messages: List[BaseMessage]
    active_agent: Literal["supervisor", "claims_validation", "rti"]
    interrupt: Optional[bool]


# -----------------------------
# TOOL (HANDOFF)
# -----------------------------
@tool
def handover(next_agent: Literal["supervisor", "claims_validation", "rti"]) -> str:
    """Switch to another agent"""
    return next_agent


# Example external tool (for demo)
@tool
def validate_claim(vrn: str) -> str:
    """Validate claim using VRN"""
    return f"Claim for {vrn} is VALID ✅"


llm_with_tools = llm.bind_tools([handover, validate_claim])

# -----------------------------
# ROUTER NODE (VISIBLE IN UI)
# -----------------------------
def router_node(state: AgentState):
    return state  # just pass through


# -----------------------------
# SUPERVISOR
# -----------------------------
def supervisor_agent(state: AgentState):
    messages = state["messages"]

    system = """You are supervisor.
Route to:
- claims_validation → claim related
- rti → RTI queries
Else answer normally.
Use tool 'handover' to switch.
"""

    response = llm_with_tools.invoke(
        [AIMessage(content=system)] + messages
    )

    if response.tool_calls:
        next_agent = response.tool_calls[0]["args"]["next_agent"]
        return {
            "messages": messages + [AIMessage(content=f"Routing to {next_agent}")],
            "active_agent": next_agent
        }

    return {
        "messages": messages + [response],
        "active_agent": "supervisor"
    }


# -----------------------------
# CLAIMS AGENT (WITH INTERRUPT + TOOL)
# -----------------------------
def claims_validation_agent(state: AgentState):
    messages = state["messages"]

    system = """You are claims agent.

Steps:
1. Ask for VRN
2. Once VRN is given → call validate_claim tool

If unrelated → use handover(supervisor)
"""

    response = llm_with_tools.invoke(
        [AIMessage(content=system)] + messages
    )

    # Tool handling
    if response.tool_calls:
        tool_call = response.tool_calls[0]

        # Handover
        if tool_call["name"] == "handover":
            next_agent = tool_call["args"]["next_agent"]
            return {
                "messages": messages + [AIMessage(content=f"Switching to {next_agent}")],
                "active_agent": next_agent
            }

        # Claim validation tool
        if tool_call["name"] == "validate_claim":
            vrn = tool_call["args"]["vrn"]
            result = validate_claim.invoke({"vrn": vrn})

            return {
                "messages": messages + [
                    AIMessage(content=f"Validating..."),
                    AIMessage(content=result)
                ],
                "active_agent": "supervisor"
            }

    return {
        "messages": messages + [response],
        "active_agent": "claims_validation"
    }


# -----------------------------
# RTI AGENT
# -----------------------------
def rti_agent(state: AgentState):
    messages = state["messages"]

    system = """You are RTI agent.
Answer RTI questions.
If unrelated → handover(supervisor)
"""

    response = llm_with_tools.invoke(
        [AIMessage(content=system)] + messages
    )

    if response.tool_calls:
        next_agent = response.tool_calls[0]["args"]["next_agent"]
        return {
            "messages": messages + [AIMessage(content=f"Switching to {next_agent}")],
            "active_agent": next_agent
        }

    return {
        "messages": messages + [response],
        "active_agent": "rti"
    }


# -----------------------------
# ROUTING LOGIC
# -----------------------------
def route_decision(state: AgentState):
    return state["active_agent"]


# -----------------------------
# GRAPH BUILD
# -----------------------------
builder = StateGraph(AgentState)

builder.add_node("router_node", router_node)
builder.add_node("supervisor_agent", supervisor_agent)
builder.add_node("claims_validation_agent", claims_validation_agent)
builder.add_node("rti_agent", rti_agent)

# START → router
builder.set_entry_point("router_node")

# Router decides next
builder.add_conditional_edges(
    "router_node",
    route_decision,
    {
        "supervisor": "supervisor_agent",
        "claims_validation": "claims_validation_agent",
        "rti": "rti_agent"
    }
)

# Loop back to router
builder.add_edge("supervisor_agent", "router_node")
builder.add_edge("claims_validation_agent", "router_node")
builder.add_edge("rti_agent", "router_node")

graph = builder.compile()
