"""
Run this ONCE before starting the LangGraph server.

  python auth_swiggy.py

A browser window will open — log in with your Swiggy account.
The token is saved to .swiggy_tokens_food.json (5-day lifetime).
After that, `langgraph dev` picks it up automatically.
"""

import asyncio
from src.utils.swiggy_mcp_client import SwiggyMCPClient


async def main() -> None:
    client = SwiggyMCPClient()
    print("Connecting to Swiggy Food MCP…")
    async with client.session() as session:
        result = await session.list_tools()
        tools = result.tools
        print(f"\n✓ Authenticated! {len(tools)} food tools available:\n")
        for t in tools:
            desc = (t.description or "")[:70]
            print(f"  {t.name:<30} {desc}")
    print("\nToken saved to .swiggy_tokens_food.json")
    print("You can now run:  langgraph dev")


if __name__ == "__main__":
    asyncio.run(main())
