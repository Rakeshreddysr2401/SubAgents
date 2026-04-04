from typing import Annotated, List, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    active_agent: Literal["supervisor", "claims_validation", "rti", "general_query"]
    pending_agent: Optional[str]
    pending_query: Optional[str] 
    lot_number: str
    uuid: str
    verified_user: bool
    user_context: dict
    claim_data: dict
    summary: Optional[str]
    video_frames: Optional[List[str]]