from src.tools.vision_tools import look_now
from src.tools.memory_tools import recall_recent
from src.tools.agent_tools import call_swiggy_agent

# recall_recent: fast text log (no LLaVA call) — always try first
# look_now:      fresh frame → LLaVA — only when text log can't answer
# call_swiggy_agent: delegate to Swiggy sub-agent for food

ALL_TOOLS = [recall_recent, look_now, call_swiggy_agent]

VIDEO_ANALYSIS_TOOLS = [recall_recent, look_now]
SUPERVISOR_TOOLS = [recall_recent, look_now, call_swiggy_agent]
