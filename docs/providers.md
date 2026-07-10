# LLM Providers

Every model the app uses is built by `src/services/llm_registry.py::build_chat_model()`
from settings resolved in `src/configs/llm.py`. Five providers:

| `LLM_PROVIDER` | Client | Notes |
|---|---|---|
| `llama_cpp` (default) | `ChatOpenAI` → any OpenAI-compatible server | llama.cpp, vLLM, LM Studio…; `llamacpp` accepted as an alias |
| `openai` | `ChatOpenAI` | `OPENAI_API_KEY` (or `LLM_API_KEY`) |
| `anthropic` | `ChatAnthropic` | `ANTHROPIC_API_KEY` (or `LLM_API_KEY`) |
| `gemini` | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY` (or `LLM_API_KEY`) |
| `ollama` | `ChatOllama` | `OLLAMA_BASE_URL` |

Generic overrides that win for any provider: `LLM_BASE_URL`, `LLM_MODEL`,
`LLM_API_KEY`, `LLM_MAX_TOKENS`. Legacy names (`LLAMA_CPP_BASE_URL`,
`SUPERVISOR_MODEL`, `OPENAI_MODEL`) remain the provider-specific defaults.

## The recommended topology: a dedicated llama.cpp server

Run the model on a separate machine (e.g. a Mac mini) so the assistant's Mac
stays light:

```bash
llama-server -m your-model.gguf --host 0.0.0.0 --port 8080 --parallel 4 --jinja
```

- `--parallel 4` creates 4 server slots; each agent pins its own slot via
  `LLM_SLOTS` (default `{"conversation": 0, "swiggy": 1, "tracker": 2,
  "planner": 3}`), forwarded as `id_slot` in the request body. Sequential
  requests from one agent land on the same slot, so its static prompt prefix
  stays in the KV cache — without pinning, requests scatter across cold slots
  and re-prefill the whole prompt every call.
- `--jinja` enables tool-call templates (required for agent tool use).
- The prompt architecture is KV-cache-disciplined: system prompts are static;
  ALL per-turn context (recalled memories + the live clock) rides a single
  trailing message so only the tail re-prefills; camera-frame image blocks are
  stripped (stable placeholder) for every agent except conversation, so
  text-only agents never pay frame token costs in their slots; MCP tool
  schemas are frozen at startup. Net effect: returning to an agent re-prefills
  only the messages that arrived since its last call.

## Per-agent overrides

`AGENT_LLM_OVERRIDES` (JSON) redirects individual agents:

```bash
AGENT_LLM_OVERRIDES={"planner": {"provider": "openai", "model": "gpt-4o"}}
```

Any subset of `provider`, `model`, `base_url`, `api_key`, `max_tokens`, `slot`.

## Cloud fallback (cooldown policy)

```bash
FALLBACK_LLM_PROVIDER=openai
FALLBACK_LLM_MODEL=gpt-4o-mini
FALLBACK_LLM_API_KEY=sk-...
```

`ResilientModelMiddleware` (`src/graph/middleware.py`) implements the policy:

1. Connection-class failure on the primary → one visible retry.
2. Still failing → the primary is marked **down for 60s** and the call goes to
   the fallback. While the cooldown lasts, calls skip the primary entirely
   (no per-turn connect timeouts against a dead server).
3. Request-shaped errors (bad schema, 4xx) never try the fallback — it would
   fail identically.
4. Nothing available → the user gets a spoken "my model server is offline"
   reply through the normal stream; the turn never 500s.

State is visible at `GET /status` (`llm.primary_available`,
`llm.primary_retry_in_s`, `llm.fallback_used_total`) and in Settings → Language
model in the UI.

## Vision, utility, and memory models

- `get_vision_llm()` — guardian mode & frame analysis. Defaults to the
  llama.cpp endpoint (`VISION_LLM_BASE_URL`/`VISION_MODEL`); set
  `VISION_LLM_PROVIDER` for a cloud VLM. Chat-side `capture_webcam` images go
  to the **calling agent's** model, so keep the chat model multimodal if you
  ask visual questions in chat.
- `get_utility_llm()` — turn summaries, long-thread summarization, Mem0-style
  extraction. Uses `UTILITY_MODEL` on OpenAI, otherwise the main model.
- Mem0 extraction follows the chat provider by default
  (`MEM0_LLM_PROVIDER=main`); set it to `openai` for noticeably better fact
  extraction when a key is available.

## Long-thread summarization

Sized for small local context windows: when an agent's history exceeds
`SUMMARIZATION_TRIGGER_TOKENS` (default 6000 approx. tokens), older messages
are folded into a summary, keeping the last `SUMMARIZATION_KEEP_MESSAGES`
(default 20). Set the trigger to `0` to disable.
