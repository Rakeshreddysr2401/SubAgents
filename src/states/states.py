from typing import Annotated, List, Literal, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    active_agent: Literal["supervisor", "claims_validation", "rti", "general_query"]
    pending_agent: Optional[str]
    pending_query: Optional[str]
    user_context: dict
    summary: Optional[str]
    video_frames: Optional[List[str]]