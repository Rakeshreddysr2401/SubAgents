import asyncio
import json
import os
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import httpx
from pydantic import AnyUrl

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientMetadata, OAuthToken, OAuthClientInformationFull
from src.configs.logging_config import get_logger

logger = get_logger(__name__)

class FileTokenStorage(TokenStorage):
    """Persist Swiggy tokens to a local JSON file."""
    def __init__(self, file_path: str = ".swiggy_tokens.json"):
        self.file_path = Path(file_path)
        self._data = self._load()

    def _load(self):
        if self.file_path.exists():
            try:
                return json.loads(self.file_path.read_text())
            except Exception as e:
                logger.error("Failed to load tokens: %s", e)
        return {"tokens": None, "client_info": None}

    def _save(self):
        self.file_path.write_text(json.dumps(self._data, indent=2))

    async def get_tokens(self):
        tokens = self._data.get("tokens")
        return OAuthToken(**tokens) if tokens else None

    async def set_tokens(self, tokens: OAuthToken):
        # Convert OAuthToken to a JSON-safe dict before saving
        if tokens:
            self._data["tokens"] = json.loads(tokens.model_dump_json()) if hasattr(tokens, "model_dump_json") else tokens.model_dump()
        else:
            self._data["tokens"] = None
        self._save()

    async def get_client_info(self):
        info = self._data.get("client_info")
        return OAuthClientInformationFull(**info) if info else None

    async def set_client_info(self, info: OAuthClientInformationFull):
        self._data["client_info"] = info.model_dump(mode='json') if hasattr(info, "model_dump") else info
        self._save()

async def handle_redirect(auth_url: str):
    print(f"\n[Swiggy Auth] Opening browser for login: {auth_url}")
    webbrowser.open(auth_url)

async def handle_callback() -> tuple[str, str | None]:
    print("\n[Swiggy Auth] Waiting for you to complete login in the browser...")
    
    future = asyncio.Future()

    async def handle_client(reader, writer):
        try:
            request_line = await reader.readline()
            request_line = request_line.decode('utf-8').strip()
            if not request_line:
                return

            method, path, version = request_line.split()
            parsed = urlparse(path)
            params = parse_qs(parsed.query)
            
            response_body = "<h1>Authentication Successful!</h1><p>You can close this window and return to the terminal.</p>"
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {len(response_body)}\r\n\r\n{response_body}"
            writer.write(response.encode('utf-8'))
            await writer.drain()
            
            if "code" in params and not future.done():
                future.set_result((params["code"][0], params.get("state", [None])[0]))
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, '127.0.0.1', 8080)
    print("[Swiggy Auth] Local server listening on http://localhost:8080/callback")
    
    try:
        # Wait indefinitely for the callback to hit our local server
        code, state = await future
    finally:
        server.close()
        await server.wait_closed()
        
    if not code:
        raise ValueError("No 'code' found in callback")
        
    return code, state

from contextlib import asynccontextmanager

class SwiggyMCPClient:
    def __init__(self, server_url: str = "https://mcp.swiggy.com/food"):
        self.server_url = server_url
        self.storage = FileTokenStorage(f".swiggy_tokens_{server_url.split('/')[-1]}.json")
        self.oauth_provider = OAuthClientProvider(
            server_url=self.server_url,
            client_metadata=OAuthClientMetadata(
                client_name="SubAgents AI",
                redirect_uris=[AnyUrl("http://localhost:8080/callback")],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="mcp:tools mcp:resources mcp:prompts"
            ),
            storage=self.storage,
            redirect_handler=handle_redirect,
            callback_handler=handle_callback,
        )

    @asynccontextmanager
    async def session(self):
        """Context manager to connect and provide a session."""
        # Increased timeout to 300 seconds (5 minutes) to give enough time for OTP login
        async with httpx.AsyncClient(auth=self.oauth_provider, follow_redirects=True, timeout=300.0) as http_client:
            transport_url = self.server_url
            async with streamable_http_client(transport_url, http_client=http_client) as streams:
                read, write, _ = streams
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.info("Connected to Swiggy MCP: %s", self.server_url)
                    yield session

async def test_client():
    # Clear any old state before testing
    token_file = Path(".swiggy_tokens_food.json")
    if token_file.exists():
        token_file.unlink()

    client = SwiggyMCPClient()
    try:
        print("Connecting to Swiggy Food MCP...")
        async with client.session() as session:
            tools = await session.list_tools()
            print(f"Success! Found tools: {[t.name for t in tools.tools]}")
    except Exception as e:
        import traceback
        print(f"Failed to connect: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_client())
