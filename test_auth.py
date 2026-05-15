import asyncio
import logging
from src.utils.swiggy_mcp_client import SwiggyMCPClient
import httpx

logging.basicConfig(level=logging.DEBUG)

async def main():
    client = SwiggyMCPClient()
    async with httpx.AsyncClient(auth=client.oauth_provider, follow_redirects=True) as http_client:
        response = await http_client.get("https://mcp.swiggy.com/food/sse")
        print(f"SSE status: {response.status_code}")
        response = await http_client.post("https://mcp.swiggy.com/food/message")
        print(f"Message status: {response.status_code}")

if __name__ == "__main__":
    asyncio.run(main())
