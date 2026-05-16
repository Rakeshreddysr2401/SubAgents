from src.tools.vision_tools import capture_webcam
from src.tools.system_tools import get_system_info, open_mac_app
from src.tools.agent_tools import call_swiggy_agent

ALL_TOOLS = [capture_webcam, get_system_info, open_mac_app, call_swiggy_agent]

SUPERVISOR_TOOLS = ALL_TOOLS
