"""System tools — interact with the Mac OS environment."""

import asyncio
import datetime
from langchain_core.tools import tool
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

@tool
async def get_system_info() -> str:
    """Returns basic system information like current date, time, and battery status."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Get battery info on macOS using async subprocess
        proc = await asyncio.create_subprocess_exec(
            "pmset", "-g", "batt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        battery_data = stdout.decode("utf-8")
        battery_status = battery_data.split('\n')[1].strip() if '\n' in battery_data else "Unknown"
    except Exception:
        battery_status = "Not available"
        
    return f"Current System Time: {now}\nBattery Status: {battery_status}"

@tool
async def open_mac_app(app_name: str) -> str:
    """Opens a Mac application by name (e.g., 'Safari', 'Music', 'Calendar')."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "open", "-a", app_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        if proc.returncode == 0:
            return f"Successfully opened {app_name}."
        else:
            return f"Failed to open {app_name}."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"
