from langchain_core.tools import tool
from src.agents.swiggy_agent import swiggy_graph
from src.states.states import AgentState
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
async def call_swiggy_agent(query: str) -> str:
    """Delegates food ordering, restaurant searching, or checkout tasks to the Swiggy Sub-Agent.
    Use this for anything related to Swiggy, delivery, food, or restaurants.
    
    Args:
        query: The user's specific food-related request.
    """
    logger.info("Delegating to Swiggy Agent: %s", query)
    
    # We must ensure we don't pass the supervisor's entire state, 
    # just the user's specific query to start a clean graph execution.
    config = {"recursion_limit": 20}
    
    try:
        result = await swiggy_graph.ainvoke({"messages": [("user", query)]}, config)
        
        # Extract the final response from the sub-agent
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content") and last_message.content:
                return str(last_message.content)
                
        return "Swiggy Agent finished but returned no response."
    except Exception as e:
        logger.error("Swiggy Agent failed: %s", e)
        return f"The Swiggy Agent encountered an error: {e}"
