from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

class AgentState(TypedDict):
    """Simplified state for the multimodal supervisor."""
    messages: Annotated[List[BaseMessage], add_messages]
    always_speak: Optional[bool]
