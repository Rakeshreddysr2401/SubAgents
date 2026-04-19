import threading
from typing import Optional
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

class WorldModel:
    """Thread-safe storage for the latest structured observation of the environment."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "people": "Not yet observed",
            "objects": "Not yet observed",
            "activity": "Not yet observed",
            "environment": "Not yet observed",
            "caption": "No observations yet",
        }

    def update(self, people: str = "", objects: str = "", activity: str = "", 
               environment: str = "", caption: str = ""):
        """Update the world model with new observations."""
        with self._lock:
            if people:
                self._state["people"] = people
            if objects:
                self._state["objects"] = objects
            if activity:
                self._state["activity"] = activity
            if environment:
                self._state["environment"] = environment
            if caption:
                self._state["caption"] = caption
        logger.debug("World model updated")

    def get_current_state(self) -> str:
        """Return a formatted string of the current state for LLM consumption."""
        with self._lock:
            return (
                f"CURRENT STRUCTURED STATE:\n"
                f"- PEOPLE: {self._state['people']}\n"
                f"- OBJECTS: {self._state['objects']}\n"
                f"- ACTIVITY: {self._state['activity']}\n"
                f"- ENVIRONMENT: {self._state['environment']}\n"
                f"- LATEST CAPTION: {self._state['caption']}"
            )

_world_model = WorldModel()

def get_world_model() -> WorldModel:
    return _world_model
