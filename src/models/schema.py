from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# API Request / Response
# ---------------------------------------------------------------------------

class LocationIn(BaseModel):
    """Browser geolocation fix, sent along with a chat turn (optional)."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None


class ChatRequest(BaseModel):
    query: str
    always_speak: bool = False
    location: LocationIn | None = None


class ResumeDecision(BaseModel):
    """One decision for one interrupted tool call.

    Shape mirrors langchain.agents.middleware.human_in_the_loop.Decision:
    type is one of "approve" | "edit" | "reject" | "respond". `edited_action`
    is required for "edit" ({"name", "args"}), `message` is used by "reject"
    (optional) and "respond" (required).
    """

    type: str
    edited_action: dict | None = None
    message: str | None = None


class ResumeRequest(BaseModel):
    decisions: List[ResumeDecision]
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


class UploadResponse(BaseModel):
    doc_id: str | None
    filename: str
    chunks: int


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class DeleteAccountRequest(BaseModel):
    password: str


class UserOut(BaseModel):
    id: str
    email: str


# ---------------------------------------------------------------------------
# Threads
# ---------------------------------------------------------------------------

class ThreadOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class RenameThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

class ReminderOut(BaseModel):
    id: str
    text: str
    due_at: str
    status: str
    created_at: str
    fired_at: str | None


# ---------------------------------------------------------------------------
# Shopping list
# ---------------------------------------------------------------------------

class ShoppingItemOut(BaseModel):
    id: str
    name: str
    quantity: str | None
    purchased: bool
    created_at: str


class AddShoppingItemRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: str | None = Field(default=None, max_length=50)


class UpdateShoppingItemRequest(BaseModel):
    purchased: bool
