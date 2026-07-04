# Setup

## Prerequisites

- **macOS** host (webcam capture, `say` TTS, and `open -a` need the host)
- **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/)
- **Docker Desktop** (Postgres, Redis, Qdrant run in containers)
- An LLM backend, either:
  - **Local**: [Ollama](https://ollama.com) or a llama.cpp server (OpenAI-compatible)
  - **OpenAI**: an API key

## 1. Start infrastructure

```bash
docker compose up -d
docker compose ps        # wait until postgres, redis, qdrant are all "healthy"
```

## 2. Install dependencies

```bash
uv sync
```

## 3. Configure environment

```bash
cp .env.example .env
# edit .env — at minimum choose your LLM + embedding providers
```

### LLM provider

- **Local (default)**: `LLM_PROVIDER=llama_cpp`, point `LLAMA_CPP_BASE_URL` at
  your server (Ollama: `http://localhost:11434/v1`) and set `SUPERVISOR_MODEL`
  to a loaded model (e.g. `gemma4:e4b`, a tool-capable model).
- **OpenAI**: `LLM_PROVIDER=openai`, set `OPENAI_API_KEY` and `OPENAI_MODEL`.

### Embedding provider

- **OpenAI (default)**: `EMBEDDING_PROVIDER=openai` (1536-dim, needs `OPENAI_API_KEY`).
- **Fully local**: `EMBEDDING_PROVIDER=ollama` and pull the model:
  ```bash
  ollama pull nomic-embed-text     # 768-dim
  ```

> ⚠️ Switching embedding providers changes vector dimensions. You must drop and
> re-create the Qdrant collections — see [memory-and-rag.md](memory-and-rag.md).

### Memory extraction LLM

Mem0 uses an LLM to extract durable facts. Local models are unreliable at this
(they hallucinate facts). Keep `MEM0_LLM_PROVIDER=openai` (`gpt-4o-mini`) in
production even when the chat model is local.

## 4. Run the app

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 2024
```

Open <http://localhost:2024>. In the UI settings bar, paste any string as the
bearer token when `AUTH_DISABLED=true` (the default); it is not verified in dev.

## 5. Optional: wake word

Instead of clicking the mic, say a wake word to activate it. The wake word wakes
the browser mic via the `/events` SSE channel (a UI tab must be open).

```bash
uv sync --extra wake            # installs the offline openWakeWord engine
```

**Single command (recommended for one machine)** — run the listener inside the
server. Set `WAKE_WORD_ENABLED=true` in `.env`, then just:

```bash
uv run uvicorn main:app --port 2024
```

**Separate process** — run the listener on its own (e.g. mic on a different
machine than the server). Leave `WAKE_WORD_ENABLED=false` and run:

```bash
uv run python wake_word.py      # downloads models on first run, then listens
```

Configure in `.env`:

```
WAKE_WORD_ENGINE=openwakeword   # offline, no API key, no audio leaves the machine
WAKE_WORD=hey_jarvis            # built-in: hey_jarvis | alexa | hey_mycroft | hey_rhasspy
WAKE_WORD_THRESHOLD=0.5         # raise toward 1.0 if it triggers too easily
```

- **Custom phrase**: openWakeWord's built-ins are the four above. For an
  arbitrary phrase, train a model (see the openWakeWord docs) and set
  `WAKE_WORD=/path/to/model.onnx`.
- **Online alternative**: `WAKE_WORD_ENGINE=google` matches any spoken phrase in
  `WAKE_WORD` but sends audio to Google and needs `SpeechRecognition` + `PyAudio`.

## Tests

```bash
uv run pytest
```

Tests are hermetic — they use fakes for the LLM, Redis (`fakeredis`), Qdrant
(`:memory:`), and Mem0. They do not require the Docker stack.
