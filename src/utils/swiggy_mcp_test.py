import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

SWIGGY_FOOD_URL = "https://mcp.swiggy.com/food"
SWIGGY_IM_URL = "https://mcp.swiggy.com/im"

async def fetch_swiggy_tools(url: str):
    """Fetch tool definitions from a Swiggy MCP server via SSE."""
    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            return tools

async def main():
    print("Fetching Food Tools...")
    try:
        food_tools = await fetch_swiggy_tools(SWIGGY_FOOD_URL)
        print(f"Found {len(food_tools.tools)} food tools.")
        for tool in food_tools.tools:
            print(f"- {tool.name}: {tool.description}")
    except Exception as e:
        import traceback
        print(f"Error fetching food tools: {e}")
        traceback.print_exc()

    print("\nFetching Instamart Tools...")
    try:
        im_tools = await fetch_swiggy_tools(SWIGGY_IM_URL)
        print(f"Found {len(im_tools.tools)} IM tools.")
        for tool in im_tools.tools:
            print(f"- {tool.name}: {tool.description}")
    except Exception as e:
        print(f"Error fetching IM tools: {e}")

if __name__ == "__main__":
    asyncio.run(main())
