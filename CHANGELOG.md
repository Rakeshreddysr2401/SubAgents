# Changelog

## 0.8.0 — 2026-07-11

Production-grade release: sellable to Mac users running their own local
VLM/LLM server, with cloud providers as first-class alternatives.

### LLM layer
- Multi-provider factory: `llama_cpp` (any OpenAI-compatible server, default) /
  `openai` / `anthropic` / `gemini` / `ollama`.
- Per-agent llama.cpp KV-cache slot pinning (`LLM_SLOTS`, matches
  `llama-server --parallel 4`), per-agent overrides (`AGENT_LLM_OVERRIDES`).
- Cloud fallback with a 60s cooldown (`FALLBACK_LLM_*`): a dead primary is
  skipped, not re-timed-out every turn; total failure returns a spoken
  degraded reply instead of a 500.
- KV-cache discipline: the live clock is a trailing message, not a per-call
  prompt mutation (and the planner finally has a clock).

### Swiggy / MCP
- Generic MCP provider framework ported from pi5_ros2_ws: no-token → zero
  network, guarded tools (failures return speakable strings), 401 → domain
  staleness + one browser notification + prompt swap, hot token reload on
  re-login (no restart).
- New `instamart` (groceries) and `dineout` (reservations) agents — the swarm
  is now 6 agents; tracker gets a collision-safe tracking-tool whitelist.
- OAuth 2.1 PKCE login script (`scripts/swiggy_login.py --verify`), tokens at
  `~/.subagents/mcp_tokens.json` (0600).
- `confirm_order` is HITL-gated: order placement always pauses for approval.

### Local-by-default memory
- Embeddings default to Ollama (`nomic-embed-text`); Mem0 extraction follows
  the chat provider (`MEM0_LLM_PROVIDER=main`) — no OpenAI key required.
- Qdrant collections are dimension-suffixed (`documents_768`, …): switching
  embedding providers is non-destructive. `scripts/migrate_qdrant.py` lists /
  drops orphans.

### Backend hardening
- `GET /status` (LLM cooldown state, MCP/token health, Postgres/Redis/Qdrant
  probes), Prometheus `GET /metrics` behind `METRICS_TOKEN`,
  `GET /system/preflight` + `scripts/preflight.py` CLI.
- CORS allow-list (`CORS_ORIGINS`, default same-origin), security headers,
  rate limiting extended to panel CRUD + `/events` connection cap.
- Auth enabled with a placeholder secret now auto-generates a persistent JWT
  secret at `~/.subagents/jwt_secret` (0600).
- launchd unit + `scripts/install_launchd.sh` (run at login, restart on crash).
- Leaked Swiggy token file removed from the tree and gitignored (rotate the
  old token — history retains it).

### LangGraph/deepagents headroom
- Per-agent summarization for long threads (sized for small local contexts).
- Time travel: `GET /threads/{id}/checkpoints` + `checkpoint_id` on `/chat`
  forks a thread from any turn boundary.
- `stream_mode="custom"`: long tools emit `{"progress": ...}` SSE lines.
- Guardian verdicts via structured output (with tolerant JSON fallback).
- Planner gains a `research` deepagents subagent (utility model + web/doc
  search) when Tavily is configured.

### Frontend
- Design-token system (`web/src/styles/tokens.css`) with a full dark theme,
  persisted theme toggle, and the 603-line monolith CSS decomposed into
  co-located token-clean sheets.
- New Settings page (theme, LLM health, integrations, services) and first-run
  Setup wizard driven by `/system/preflight` (auto-shown when not ready).
- Time-travel UI: hover a message → "edit & resend from here".
- Live progress lines in the thinking bubble; login-expired toasts.
- Vitest + React Testing Library: SSE parser, InterruptCard decisions,
  themeStore (`npm run test`).

### Fixes
- Camera frames were silently never sent (missing capture canvas).
- Chrome speechSynthesis reliability (keepalive + utterance chaining).
- Default LLM endpoint no longer points at a personal hostname.
