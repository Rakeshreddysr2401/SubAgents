from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# API Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str
    always_speak: bool = False


class MessageItem(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    messages: List[MessageItem] = Field(
        default_factory=list,
        description="Full conversation history for this thread",
    )
