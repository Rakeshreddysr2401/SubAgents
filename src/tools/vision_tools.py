from .claim_tools import validate_claim_api
from .handover_tool import handover
from .vision_tools import analyze_with_vision


supervisor_tools = [handover]
claim_validate_tools = [validate_claim_api, handover]
rti_tools = [handover]
general_query_tools = [handover, analyze_with_vision]