from src.tools.vision_tools import look_now
from src.tools.memory_tools import recall_recent

# recall_recent: fast text log (no LLaVA call) — always try first
# look_now:      fresh frame → LLaVA — only when text log can't answer

ALL_TOOLS = [recall_recent, look_now]

VIDEO_ANALYSIS_TOOLS = [recall_recent, look_now]
SUPERVISOR_TOOLS = [recall_recent, look_now]
