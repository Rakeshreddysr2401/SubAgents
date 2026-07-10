"""MCP provider framework — remote tool servers (Swiggy food/instamart/dineout).

Ported from pi5_ros2_ws's battle-tested services/mcp.py. One ProviderSpec per
remote MCP server; adding a future provider (movie tickets, bus tickets, …) is
one PROVIDERS entry here plus the normal "add an agent" recipe in CLAUDE.md.

Token model: providers that share a login share an *auth domain*. Tokens live
in ~/.subagents/mcp_tokens.json (written by scripts/swiggy_login.py, keyed by
domain); a legacy env var (spec.token_env) overrides the file when set. No
token → the provider loads zero tools and NEVER touches the network — hermetic
tests and offline boots rely on that.

Reload safety (KV-cache discipline):
- Tool objects and their LLM-visible schemas are frozen at process start —
  the graph's ToolNodes capture the lists at boot. Going from never-configured
  to configured therefore needs one server restart.
- A token *refresh* is only a header mutation: langchain-mcp-adapters opens a
  fresh MCP session per tool call from the connection dict captured at load,
  so updating headers["Authorization"] in place re-arms the existing tool
  objects. Same objects, same schemas, zero KV-cache impact.
- refresh_tokens_if_changed() runs only at the top of /chat and /chat/resume
  (one os.stat per turn), never inside tool calls, so headers and provider
  state are stable within any single LLM call.

Staleness: a 401 during a tool call marks the whole auth domain stale, pushes
ONE {"type": "mcp_auth_expired"} event to connected browsers, and the guarded
tool returns a graceful string to the LLM instead of raising.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_FILE = "~/.subagents/mcp_tokens.json"


@dataclass(frozen=True)
class ProviderSpec:
    name: str            # PROVIDERS key, e.g. "swiggy_food"
    url: str             # default MCP endpoint
    url_env: str         # env var overriding the URL
    auth_domain: str     # key into mcp_tokens.json domains, e.g. "swiggy"
    token_env: str = ""  # legacy env override for the bearer token
    login_hint: str = "uv run python scripts/swiggy_login.py"


PROVIDERS: dict[str, ProviderSpec] = {
    "swiggy_food": ProviderSpec(
        "swiggy_food", "https://mcp.swiggy.com/food",
        "SWIGGY_FOOD_MCP_URL", "swiggy", "SWIGGY_ACCESS_TOKEN"),
    "swiggy_instamart": ProviderSpec(
        "swiggy_instamart", "https://mcp.swiggy.com/im",  # yes, /im — not /instamart
        "SWIGGY_INSTAMART_MCP_URL", "swiggy", "SWIGGY_ACCESS_TOKEN"),
    "swiggy_dineout": ProviderSpec(
        "swiggy_dineout", "https://mcp.swiggy.com/dineout",
        "SWIGGY_DINEOUT_MCP_URL", "swiggy", "SWIGGY_ACCESS_TOKEN"),
}

# ── Module state (all guarded by _lock) ──────────────────────────────────────

_lock = threading.Lock()
_tools: dict[str, list] = {}     # provider name → guarded tool list
_headers: dict[str, dict] = {}   # provider name → the live headers dict
_stale: set[str] = set()         # auth domains with a dead token
_notified: set[str] = set()      # domains already pushed to the browser
_token_file_mtime: float = 0.0
_warned_malformed = False


def _token_file_path() -> str:
    return os.path.expanduser(os.getenv("SUBAGENTS_MCP_TOKENS", _DEFAULT_TOKEN_FILE))


def _read_token_file() -> dict:
    """domains dict from the token file, {} on absent/malformed (warn once)."""
    global _warned_malformed
    path = _token_file_path()
    try:
        with open(path) as f:
            data = json.load(f)
        domains = data.get("domains", {})
        if not isinstance(domains, dict):
            raise ValueError("domains is not an object")
        return domains
    except FileNotFoundError:
        return {}
    except Exception as e:
        if not _warned_malformed:
            logger.warning("mcp: %s malformed (%s) — treating as absent", path, e)
            _warned_malformed = True
        return {}


def _resolve_token(spec: ProviderSpec) -> str:
    if spec.token_env:
        env = os.getenv(spec.token_env, "")
        if env:
            return env
    entry = _read_token_file().get(spec.auth_domain, {})
    return entry.get("access_token", "") if isinstance(entry, dict) else ""


def _root_cause(exc: BaseException) -> BaseException:
    """Drill through ExceptionGroup/TaskGroup wrappers to the real error.

    The MCP client raises its failures inside an anyio TaskGroup, so the
    top-level message is the useless "unhandled errors in a TaskGroup" —
    unwrap to the leaf (e.g. the httpx 401) so the log says what went wrong."""
    seen = set()
    while True:
        if id(exc) in seen:
            return exc
        seen.add(id(exc))
        subs = getattr(exc, "exceptions", None)
        if subs:
            exc = subs[0]
        elif exc.__cause__ is not None:
            exc = exc.__cause__
        else:
            return exc


def _is_auth_error(cause: BaseException) -> bool:
    text = str(cause)
    if "401" in text or "Unauthorized" in text or "invalid_token" in text:
        return True
    status = getattr(getattr(cause, "response", None), "status_code", None)
    return status == 401


# ── Loading ──────────────────────────────────────────────────────────────────

async def _fetch_tools(spec: ProviderSpec, headers: dict) -> list:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    url = os.getenv(spec.url_env, "") or spec.url
    client = MultiServerMCPClient(
        {
            spec.name: {
                "transport": "streamable_http",
                "url": url,
                "headers": headers,
            }
        }
    )
    return await client.get_tools()


async def load_provider_tools(name: str, timeout: float | None = None) -> list:
    """Load (once) and cache the guarded tool list for a provider.

    No token → [] with zero network. Any failure → [] with the root cause
    logged (plus a login hint on 401). Idempotent — called from the lifespan.
    """
    from src.configs.settings import get_settings

    spec = PROVIDERS[name]
    with _lock:
        if name in _tools:
            return _tools[name]
        token = _resolve_token(spec)
        if not token:
            logger.info("mcp %s: no token — disabled (run %s)", name, spec.login_hint)
            _tools[name] = []
            return _tools[name]
        # This exact dict object is captured by the MCP connection; token
        # refresh mutates it in place (see module docstring).
        headers = {"Authorization": f"Bearer {token}"}

    if timeout is None:
        timeout = get_settings().mcp_load_timeout_seconds
    try:
        raw = await asyncio.wait_for(_fetch_tools(spec, headers), timeout=timeout)
        guarded = [_guard_tool(t, spec) for t in raw]
    except Exception as e:
        cause = _root_cause(e)
        hint = f" (run {spec.login_hint})" if _is_auth_error(cause) else ""
        logger.warning("mcp %s unavailable — tools disabled: %s%s", name, cause, hint)
        with _lock:
            _tools[name] = []
        return _tools[name]

    global _token_file_mtime
    with _lock:
        _tools[name] = guarded
        _headers[name] = headers
        try:
            _token_file_mtime = os.stat(_token_file_path()).st_mtime
        except OSError:
            pass
    logger.info("mcp %s: %d tools loaded", name, len(guarded))
    return guarded


# ── Runtime guard ────────────────────────────────────────────────────────────

def _guard_tool(tool, spec: ProviderSpec):
    """Wrap an MCP tool so runtime failures degrade instead of raising.

    The wrapper keeps name/description/args_schema byte-identical to the
    original — the LLM-visible schema is part of the llama.cpp prompt prefix
    and must not change (KV-cache rule)."""
    from langchain_core.tools import StructuredTool

    async def guarded(**kwargs) -> str:
        try:
            return await tool.coroutine(**kwargs)
        except Exception as e:
            cause = _root_cause(e)
            if _is_auth_error(cause):
                mark_domain_stale(spec.auth_domain, str(cause))
                return (
                    "This service's login has expired. Tell the user the app "
                    "needs to be re-authorized (a notification with "
                    "instructions was sent), then transfer_to_conversation."
                )
            logger.warning("mcp %s tool %s failed: %s", spec.name, tool.name, cause)
            return f"The {tool.name} call failed ({cause}). Tell the user honestly."

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=guarded,
    )


def mark_domain_stale(domain: str, cause: str) -> None:
    """Flag a dead login and notify the browser exactly once."""
    with _lock:
        _stale.add(domain)
        if domain in _notified:
            return
        _notified.add(domain)  # before sending — never double-send
    logger.warning("mcp: auth domain %s stale — %s", domain, cause)
    hint = next(
        (s.login_hint for s in PROVIDERS.values() if s.auth_domain == domain),
        "the login script",
    )
    try:
        from src.services.event_broker import get_broker

        # Runs inside a tool coroutine, i.e. on the app's event loop — safe.
        get_broker().broadcast({
            "type": "mcp_auth_expired",
            "domain": domain,
            "message": (
                f"The {domain} login has expired, so those features are "
                f"paused. Run {hint} to re-authorize — no restart needed."
            ),
        })
    except Exception as e:
        logger.warning("mcp: stale-token notification failed: %s", e)


# ── Refresh + status ─────────────────────────────────────────────────────────

def refresh_tokens_if_changed() -> None:
    """Pick up a re-login without restarting: one stat, header swap in place.

    Called at the top of /chat and /chat/resume only."""
    global _token_file_mtime
    with _lock:
        try:
            mtime = os.stat(_token_file_path()).st_mtime
        except OSError:
            return
        if mtime <= _token_file_mtime:
            return
        _token_file_mtime = mtime
        domains = _read_token_file()
        for name, headers in _headers.items():
            spec = PROVIDERS[name]
            if spec.token_env and os.getenv(spec.token_env, ""):
                continue  # env override in force; file change irrelevant
            entry = domains.get(spec.auth_domain, {})
            token = entry.get("access_token", "") if isinstance(entry, dict) else ""
            if token and headers.get("Authorization") != f"Bearer {token}":
                headers["Authorization"] = f"Bearer {token}"
                _stale.discard(spec.auth_domain)
                _notified.discard(spec.auth_domain)
                logger.info("mcp %s: token refreshed — provider re-armed", name)


def provider_ok(name: str) -> bool:
    """Tools loaded and the login isn't known-dead — drives the prompt swap."""
    with _lock:
        return bool(_tools.get(name)) and PROVIDERS[name].auth_domain not in _stale


def status() -> dict:
    """Provider/token health for /status. Never contains token values."""
    with _lock:
        providers = {
            name: {
                "tools": len(_tools.get(name, [])),
                "ok": bool(_tools.get(name)) and spec.auth_domain not in _stale,
            }
            for name, spec in PROVIDERS.items()
        }
        domains = _read_token_file()
        tokens = {}
        for domain in {s.auth_domain for s in PROVIDERS.values()}:
            env_set = any(
                s.token_env and os.getenv(s.token_env, "")
                for s in PROVIDERS.values() if s.auth_domain == domain
            )
            entry = domains.get(domain, {})
            if not isinstance(entry, dict):
                entry = {}
            expires_at = entry.get("expires_at")
            tokens[domain] = {
                "source": "env" if env_set else ("file" if entry.get("access_token") else "none"),
                "expires_at": expires_at,
                "days_left": round((expires_at - time.time()) / 86400, 1) if expires_at else None,
                "stale": domain in _stale,
            }
        return {"providers": providers, "tokens": tokens}


def reset_state() -> None:
    """Test seam: forget every loaded provider/token."""
    global _token_file_mtime, _warned_malformed
    with _lock:
        _tools.clear()
        _headers.clear()
        _stale.clear()
        _notified.clear()
        _token_file_mtime = 0.0
        _warned_malformed = False
