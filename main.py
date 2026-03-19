import os
from typing import TypedDict, List, Dict
from fastapi import FastAPI
from dotenv import load_dotenv

from langgraph.graph import StateGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool

# =========================
# ENV SETUP
# =========================
load_dotenv()

# =========================
# MEMORY STORE (in-memory)
# =========================
memory_store: Dict[str, List] = {}

def get_memory(conversation_id: str):
    return memory_store.get(conversation_id, [])

def save_memory(conversation_id: str, messages: List):
    memory_store[conversation_id] = messages

# =========================
# STATE
# =========================
class AgentState(TypedDict):
    conversation_id: str
    messages: List
    user_query: str

# =========================
# LLM (Gemini)
# =========================
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    temperature=0
)

# =========================
# TOOLS
# =========================

# Web Tool (Dummy / Replace with Tavily)
@tool
def web_search(query: str):
    """Search the web for information"""
    return f"[WEB RESULT]: Top results for '{query}'"

# ROS2 Robot Tool (Dummy)
@tool
def move_robot(direction: str):
    """Move robot in a direction (left/right/forward/back)"""
    return f"[ROBOT]: Moving {direction}"

# =========================
# AGENTS
# =========================

# General Agent (normal chat)
def general_agent(state: AgentState):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}


# Web Agent
llm_web = llm.bind_tools([web_search])

def web_agent(state: AgentState):
    response = llm_web.invoke(state["messages"])
    return {"messages": [response]}


# Robot Agent (force tool)
llm_robot = llm.bind_tools([move_robot], tool_choice="required")

def robot_agent(state: AgentState):
    response = llm_robot.invoke(state["messages"])
    return {"messages": [response]}


# =========================
# ROUTER (MAIN AGENT)
# =========================
def router(state: AgentState):
    query = state["user_query"].lower()

    if "search" in query or "news" in query:
        return "web_agent"
    elif "move" in query or "robot" in query:
        return "robot_agent"
    else:
        return "general_agent"


# =========================
# GRAPH
# =========================
builder = StateGraph(AgentState)

builder.add_node("router", router)
builder.add_node("general_agent", general_agent)
builder.add_node("web_agent", web_agent)
builder.add_node("robot_agent", robot_agent)

builder.set_entry_point("router")

builder.add_conditional_edges(
    "router",
    router,
    {
        "general_agent": "general_agent",
        "web_agent": "web_agent",
        "robot_agent": "robot_agent",
    }
)

builder.set_finish_point("general_agent")
builder.set_finish_point("web_agent")
builder.set_finish_point("robot_agent")

graph = builder.compile()

# =========================
# FASTAPI
# =========================
app = FastAPI()

@app.post("/chat")
async def chat(data: dict):
    conversation_id = data.get("conversationId")
    user_query = data.get("query")

    if not conversation_id or not user_query:
        return {"error": "conversationId and query are required"}

    # Load memory
    messages = get_memory(conversation_id)

    # Add user message
    messages.append({"role": "user", "content": user_query})

    # Run graph
    state = {
        "conversation_id": conversation_id,
        "messages": messages,
        "user_query": user_query
    }

    result = graph.invoke(state)

    ai_msg = result["messages"][-1]

    # Append AI response
    messages.append(ai_msg)

    # Save memory
    save_memory(conversation_id, messages)

    return {
        "response": ai_msg.content,
        "conversationId": conversation_id,
        "messages": messages
    }


# =========================
# RUN (optional)
# =========================
# uvicorn main:app --reload