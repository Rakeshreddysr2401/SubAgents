from src.tools.world_tools import recall_world
from src.tools.memory_tools import recall_recent
from src.tools.vision_tools import look_now

# Tool priority: most → least efficient
#   recall_world   → instant, world model  (current state)
#   recall_recent  → instant, event log    (last 5 min text + YOLO)
#   look_now       → 2-10s, moondream VLM  (visual detail)
ALL_TOOLS = [recall_world, recall_recent, look_now]

VIDEO_ANALYSIS_TOOLS = ALL_TOOLS
SUPERVISOR_TOOLS     = ALL_TOOLS
