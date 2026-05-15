import asyncio
import logging
from src.utils.swiggy_mcp_client import SwiggyMCPClient

logging.basicConfig(level=logging.DEBUG)

async def main():
    client = SwiggyMCPClient()
    try:
        async with client.session() as session:
            tools = await session.list_tools()
            print(f"Found tools: {[t.name for t in tools.tools]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
