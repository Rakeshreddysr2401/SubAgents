from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from dotenv import load_dotenv
import os

load_dotenv()

llm = ChatOpenAI(
    model="gpt-4o",
    api_key=os.getenv("OPENAI_API_KEY")
)

# -----------------------------
# STATE
# -----------------------------
class AgentState(TypedDict):
    messages: List[BaseMessage]


# -----------------------------
# NODE (LLM CALL)
# -----------------------------
def chatbot_node(state: AgentState):
    response = llm.invoke(state["messages"])

    return {
        "messages": state["messages"] + [response]
    }


# -----------------------------
# GRAPH BUILD
# -----------------------------
builder = StateGraph(AgentState)

builder.add_node("chatbot", chatbot_node)

builder.set_entry_point("chatbot")

builder.add_edge("chatbot", END)

graph = builder.compile()