from typing import List

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# API Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str


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


# ---------------------------------------------------------------------------
# Claim Validation Payload
# ---------------------------------------------------------------------------

class ClaimValidatePayload(BaseModel):
    claim_number: str = Field(
        description="Claim reference number e.g. 101-038-0877 or 1010380877 (auto-normalised by the tool)"
    )
    vrn: str = Field(
        description="Vehicle Registration Number exactly as the user typed it e.g. UK8909"
    )
    fullname: str = Field(
        description=(
            "Claimant's full name — EXACT characters from the user's message, "
            "character by character. Do NOT retype or alter any letters."
        )
    )
    dob: str = Field(
        description="Date of birth in ISO 8601: YYYY-MM-DDTHH:mm:ss.sssZ e.g. 2000-01-30T18:30:00.000Z"
    )
    date_of_incident: str = Field(
        description="Date of incident in DD-MM-YYYY format e.g. 31-03-2025"
    )
