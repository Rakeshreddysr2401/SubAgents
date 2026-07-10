# Swiggy MCP Integration (food · instamart · dineout)

The `swiggy`, `instamart`, and `dineout` agents get their ordering tools from
Swiggy's official remote MCP servers. The framework
(`src/services/mcp_providers.py`) is provider-generic — adding another remote
MCP service is one `PROVIDERS` entry plus the normal "add an agent" recipe in
CLAUDE.md.

| Provider | Endpoint | Agent |
|---|---|---|
| `swiggy_food` | `https://mcp.swiggy.com/food` | swiggy |
| `swiggy_instamart` | `https://mcp.swiggy.com/im` | instamart |
| `swiggy_dineout` | `https://mcp.swiggy.com/dineout` | dineout |

All three share one **auth domain** (`swiggy`): one login covers them.

## Logging in

```bash
uv run python scripts/swiggy_login.py --verify
```

OAuth 2.1 PKCE with dynamic client registration; a localhost callback catches
the redirect (use `--no-browser` + an SSH tunnel on a headless box). Tokens are
written atomically to `~/.subagents/mcp_tokens.json` (chmod 600, keyed by
domain). `--verify` runs a real MCP `initialize` + `tools/list` handshake
against all three servers.

The access token lasts ~5 days and has **no refresh flow** — expiry is handled
by graceful degradation + a re-login nudge, not by refresh tokens.

## Lifecycle & failure behavior

- **No token → zero network.** The app boots normally offline; ordering agents
  carry only their non-MCP tools plus an "unavailable" prompt note so the
  model tells the user instead of flailing.
- **Runtime failures degrade, never crash.** Every MCP tool is wrapped
  (`_guard_tool`): errors come back as strings the model can speak. A 401
  marks the whole `swiggy` domain **stale**, pushes ONE
  `{"type": "mcp_auth_expired"}` browser notification, and swaps the agents'
  prompts to the unavailable note.
- **Re-login without restart.** At the top of every `/chat`, the token file's
  mtime is checked (one `os.stat`); a new token swaps the `Authorization`
  header in place on the live connections and re-arms the providers. Only a
  *never-configured* server needs one restart after the first login (tool
  schemas are frozen at startup — a KV-cache discipline, see
  docs/providers.md).
- **Spending is gated.** `confirm_order` (the shared order-placement tool name
  on food + instamart) is in `GATED_TOOL_NAMES`, so order placement always
  pauses for human approval in the UI — enforcement at the tool boundary, not
  in prompts.

## Health

`GET /status` → `mcp.providers` (tool counts, ok) and `mcp.tokens.swiggy`
(`source`, `days_left`, `stale`) — never token values. The same data renders in
Settings → Integrations, and the preflight (`/system/preflight`, Setup wizard)
flags an expired login.

## Tracker tool whitelist (don't "fix" this)

The food and instamart servers **share tool names** (`get_addresses`,
`confirm_order`, `get_payment_options`, …). The tracker agent therefore carries
only the non-colliding read-only tracking subset (`_TRACKING_TOOL_NAMES` in
`src/tools/__init__.py`) — splicing both full sets into one agent would put
ambiguous duplicate tools in a single ToolNode.
