"""
Swiggy MCP OAuth client.

Opens a browser for your Swiggy account login, exchanges the code for a token,
and persists it to .swiggy_tokens_food.json.  No pre-registration with Swiggy
needed — client_id "swiggy-mcp" is the public MCP client ID they expose.

Run auth_swiggy.py once to authenticate before starting the server.
"""

import asyncio
import json
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import AnyUrl

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from src.configs.logging_config import get_logger

logger = get_logger(__name__)

CALLBACK_PORT = 8080
CALLBACK_URI = f"http://localhost:{CALLBACK_PORT}/callback"


class FileTokenStorage(TokenStorage):
    """Persist Swiggy OAuth tokens to a local JSON file."""

    def __init__(self, file_path: str = ".swiggy_tokens_food.json"):
        self.file_path = Path(file_path)
        self._data = self._load()

    def _load(self) -> dict:
        if self.file_path.exists():
            try:
                return json.loads(self.file_path.read_text())
            except Exception as e:
                logger.warning("Could not load token file: %s", e)
        return {"tokens": None, "client_info": None}

    def _save(self) -> None:
        self.file_path.write_text(json.dumps(self._data, indent=2))

    async def get_tokens(self) -> OAuthToken | None:
        tokens = self._data.get("tokens")
        return OAuthToken(**tokens) if tokens else None

    async def set_tokens(self, tokens: OAuthToken | None) -> None:
        if tokens:
            self._data["tokens"] = (
                json.loads(tokens.model_dump_json())
                if hasattr(tokens, "model_dump_json")
                else tokens.model_dump()
            )
        else:
            self._data["tokens"] = None
        self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        info = self._data.get("client_info")
        return OAuthClientInformationFull(**info) if info else None

    async def set_client_info(self, info: OAuthClientInformationFull) -> None:
        self._data["client_info"] = (
            info.model_dump(mode="json") if hasattr(info, "model_dump") else info
        )
        self._save()


async def _open_browser(auth_url: str) -> None:
    print(f"\n[Swiggy Auth] Opening browser → {auth_url}")
    webbrowser.open(auth_url)


async def _wait_for_callback() -> tuple[str, str | None]:
    """Start a one-shot TCP server on CALLBACK_PORT and wait for the OAuth redirect."""
    print(f"[Swiggy Auth] Waiting for login… (listening on {CALLBACK_URI})")
    future: asyncio.Future[tuple[str, str | None]] = asyncio.get_event_loop().create_future()

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = (await reader.readline()).decode().strip()
            if not line:
                return
            _, path, _ = line.split()
            params = parse_qs(urlparse(path).query)
            body = b"<h1>Login successful! You can close this tab.</h1>"
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
                + body
            )
            await writer.drain()
            if "code" in params and not future.done():
                future.set_result((params["code"][0], params.get("state", [None])[0]))
        except Exception as exc:
            logger.debug("Callback handler error: %s", exc)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(_handle, "127.0.0.1", CALLBACK_PORT)
    try:
        code, state = await future
    finally:
        server.close()
        await server.wait_closed()

    if not code:
        raise ValueError("No 'code' in OAuth callback")
    return code, state


class SwiggyMCPClient:
    """
    Authenticated MCP client for Swiggy food APIs.

    On first use, opens a browser window for Swiggy login and saves the token.
    Subsequent uses load the saved token automatically (5-day lifetime).
    """

    def __init__(self, server_url: str = "https://mcp.swiggy.com/food"):
        self.server_url = server_url
        token_file = f".swiggy_tokens_{server_url.split('/')[-1]}.json"
        self.storage = FileTokenStorage(token_file)
        self.oauth_provider = OAuthClientProvider(
            server_url=self.server_url,
            client_metadata=OAuthClientMetadata(
                client_name="SubAgents AI",
                redirect_uris=[AnyUrl(CALLBACK_URI)],
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
                scope="mcp:tools mcp:resources mcp:prompts",
            ),
            storage=self.storage,
            redirect_handler=_open_browser,
            callback_handler=_wait_for_callback,
        )

    @asynccontextmanager
    async def session(self):
        """Async context manager — yields an authenticated MCP ClientSession."""
        async with httpx.AsyncClient(
            auth=self.oauth_provider,
            follow_redirects=True,
            timeout=300.0,  # 5 min — enough time to complete browser login
        ) as http_client:
            async with streamable_http_client(
                self.server_url, http_client=http_client
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.info("Connected to Swiggy MCP: %s", self.server_url)
                    yield session
