"""Central application settings — single source of truth for all env config.

Every module should use `get_settings()` instead of scattered `os.getenv` calls.
Values load from the process environment first, then `.env`.
"""

import json
from functools import lru_cache
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Populate os.environ from .env so third-party libs (OpenAI, Tavily, …) that
# read the environment directly see the same values as Settings.
load_dotenv()

# Known embedding dimensions per provider default model.
_EMBEDDING_DIMS = {
    "openai": 1536,  # text-embedding-3-small
    "ollama": 768,   # nomic-embed-text
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM ---
    # llama_cpp = any OpenAI-compatible self-hosted server (llama.cpp, vLLM,
    # LM Studio, …); "llamacpp" is accepted as an alias.
    llm_provider: Literal["llama_cpp", "openai", "anthropic", "gemini", "ollama"] = Field(
        "llama_cpp", alias="LLM_PROVIDER"
    )
    # Generic overrides that win for any provider. Empty = derive from the
    # provider-specific legacy fields below.
    llm_base_url: str = Field("", alias="LLM_BASE_URL")
    llm_model: str = Field("", alias="LLM_MODEL")
    llm_api_key: str = Field("", alias="LLM_API_KEY")
    llm_max_tokens: Optional[int] = Field(None, alias="LLM_MAX_TOKENS")
    # Per-agent llama.cpp KV-cache slot pinning (server needs --parallel N).
    # Each agent's requests land on its own slot so the static prompt prefix
    # stays cached — without pinning, a multi-slot server scatters requests
    # across cold slots and re-prefills the whole prompt every call.
    # JSON {agent_name: slot}; -1 or absent = no pin. Applied only when
    # llm_provider=llama_cpp.
    llm_slots_json: str = Field(
        '{"conversation": 0, "swiggy": 1, "tracker": 2, "planner": 3}',
        alias="LLM_SLOTS",
    )
    # Per-agent full overrides: JSON {agent: {provider?, model?, base_url?,
    # api_key?, max_tokens?, slot?}}. Lets one agent run on a different
    # provider/model without disturbing the others.
    agent_llm_overrides_json: str = Field("{}", alias="AGENT_LLM_OVERRIDES")
    # Cloud fallback: used automatically while the primary LLM is in its
    # post-failure cooldown window. Empty provider/model = no fallback.
    fallback_llm_provider: str = Field("", alias="FALLBACK_LLM_PROVIDER")
    fallback_llm_model: str = Field("", alias="FALLBACK_LLM_MODEL")
    fallback_llm_api_key: str = Field("", alias="FALLBACK_LLM_API_KEY")
    fallback_llm_base_url: str = Field("", alias="FALLBACK_LLM_BASE_URL")
    # Point at your LLM server (any OpenAI-compatible endpoint), e.g. a
    # mac-mini on the LAN running `llama-server --parallel 4`.
    llama_cpp_base_url: str = Field(
        "http://localhost:8080/v1", alias="LLAMA_CPP_BASE_URL"
    )
    # Model name loaded in the llama.cpp server (legacy env name kept)
    model_name: str = Field("multimodal-model", alias="SUPERVISOR_MODEL")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    # Small/cheap model for background work: turn summaries, Mem0 extraction, frame descriptions
    utility_model: str = Field("gpt-4o-mini", alias="UTILITY_MODEL")
    # Dedicated vision (VLM) endpoint — e.g. a mac-mini llama.cpp server.
    # Vision consumers (guardian mode, frame analysis) always hit this, so the
    # chat model can run anywhere without losing vision. Empty provider means
    # "OpenAI-compatible" (llama.cpp); empty URL/model fall back to
    # LLAMA_CPP_BASE_URL / SUPERVISOR_MODEL.
    vision_llm_provider: Literal["", "llama_cpp", "openai", "anthropic", "gemini", "ollama"] = (
        Field("", alias="VISION_LLM_PROVIDER")
    )
    vision_llm_base_url: str = Field("", alias="VISION_LLM_BASE_URL")
    vision_model: str = Field("", alias="VISION_MODEL")

    # --- Embeddings ---
    # ollama (default) keeps the product fully local / zero-key; openai is the
    # opt-in quality upgrade. OLLAMA_BASE_URL may point at a LAN server.
    embedding_provider: Literal["openai", "ollama"] = Field("ollama", alias="EMBEDDING_PROVIDER")
    openai_embedding_model: str = Field("text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")
    ollama_embedding_model: str = Field("nomic-embed-text", alias="OLLAMA_EMBEDDING_MODEL")
    ollama_base_url: str = Field("http://localhost:11434", alias="OLLAMA_BASE_URL")
    # Explicit override; otherwise derived from provider. Changing provider/dim
    # requires re-creating Qdrant collections (see docs/memory-and-rag.md).
    embedding_dim_override: Optional[int] = Field(None, alias="EMBEDDING_DIM")

    # --- Infrastructure ---
    postgres_dsn: str = Field(
        "postgresql://subagents:subagents@localhost:5432/subagents", alias="POSTGRES_DSN"
    )
    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    qdrant_url: str = Field("http://localhost:6333", alias="QDRANT_URL")

    # --- Memory (Mem0) ---
    # "main" (default) = use the same provider as the chat LLM, so a zero-key
    # local install works out of the box. Fact extraction is noticeably more
    # reliable on OpenAI — set MEM0_LLM_PROVIDER=openai to upgrade.
    mem0_llm_provider: Literal["main", "openai", "llama_cpp", "ollama"] = Field(
        "main", alias="MEM0_LLM_PROVIDER"
    )
    mem0_llm_model: str = Field("gpt-4o-mini", alias="MEM0_LLM_MODEL")
    mem0_collection_name: str = Field("mem0_memories", alias="MEM0_COLLECTION")
    recall_limit: int = Field(5, alias="MEM0_RECALL_LIMIT")

    # --- RAG ---
    # Base collection names; the public accessors below suffix them with the
    # embedding dimension (documents_768, …) so switching embedding providers
    # is non-destructive: each dim gets its own collections, old ones are
    # orphaned rather than corrupted (clean up with scripts/migrate_qdrant.py).
    documents_collection_name: str = Field("documents", alias="DOCUMENTS_COLLECTION")
    history_collection_name: str = Field("history", alias="HISTORY_COLLECTION")
    search_cache_collection_name: str = Field("search_cache", alias="SEARCH_CACHE_COLLECTION")
    chunk_size: int = Field(1000, alias="RAG_CHUNK_SIZE")
    chunk_overlap: int = Field(150, alias="RAG_CHUNK_OVERLAP")
    upload_max_bytes: int = Field(10 * 1024 * 1024, alias="UPLOAD_MAX_BYTES")
    web_cache_score_threshold: float = Field(0.92, alias="WEB_CACHE_SCORE_THRESHOLD")
    web_cache_ttl_seconds: int = Field(3600, alias="WEB_CACHE_TTL_SECONDS")
    web_cache_semantic_max_age_seconds: int = Field(
        24 * 3600, alias="WEB_CACHE_SEMANTIC_MAX_AGE_SECONDS"
    )
    # Vision history indexing: reuse (index assistant's own visual answer),
    # llm (extra describe call), off
    vision_indexing: Literal["reuse", "llm", "off"] = Field("reuse", alias="VISION_INDEXING")

    # --- Auth ---
    auth_disabled: bool = Field(True, alias="AUTH_DISABLED")
    jwt_secret: str = Field("change-me-in-production", alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    access_token_ttl_minutes: int = Field(15, alias="ACCESS_TOKEN_TTL_MINUTES")
    refresh_token_ttl_days: int = Field(7, alias="REFRESH_TOKEN_TTL_DAYS")
    # Cookies need Secure=false to work over plain http in local dev; set true in prod (https).
    cookie_secure: bool = Field(False, alias="COOKIE_SECURE")

    # --- Agents / runtime ---
    max_agent_visits: int = Field(3, alias="MAX_AGENT_VISITS")
    frame_ttl_seconds: int = Field(120, alias="FRAME_TTL_SECONDS")
    chat_timeout_seconds: int = Field(120, alias="CHAT_TIMEOUT_SECONDS")
    rate_limit_per_minute: int = Field(20, alias="RATE_LIMIT_PER_MINUTE")
    # Speak replies through the host Mac's `say` command as well (the browser
    # speaks via speechSynthesis regardless — this is only for the server box).
    host_tts_enabled: bool = Field(False, alias="HOST_TTS_ENABLED")
    # How often the reminder scheduler checks for due reminders.
    reminder_poll_seconds: int = Field(15, alias="REMINDER_POLL_SECONDS")
    # Guardian mode: how often to look at the camera, and the minimum gap
    # between two alerts to the same user.
    guardian_interval_seconds: int = Field(20, alias="GUARDIAN_INTERVAL_SECONDS")
    guardian_alert_cooldown_seconds: int = Field(120, alias="GUARDIAN_ALERT_COOLDOWN_SECONDS")
    # Internet-radio stations for the browser music player, as a JSON list of
    # {"name", "url"} objects. Defaults to a couple of free public streams.
    music_stations_json: str = Field(
        '[{"name": "Groove Salad (SomaFM)", "url": "https://ice1.somafm.com/groovesalad-128-mp3"},'
        ' {"name": "Radio Paradise", "url": "https://stream.radioparadise.com/mp3-128"},'
        ' {"name": "Drone Zone (SomaFM)", "url": "https://ice1.somafm.com/dronezone-128-mp3"}]',
        alias="MUSIC_STATIONS",
    )

    # --- Wake word ---
    # Run the listener inside the server process (single command) vs. only via
    # the standalone `uv run python wake_word.py` script.
    wake_word_enabled: bool = Field(False, alias="WAKE_WORD_ENABLED")
    wake_word_engine: Literal["openwakeword", "google"] = Field(
        "openwakeword", alias="WAKE_WORD_ENGINE"
    )
    # openwakeword: a built-in model name (hey_jarvis, alexa, hey_mycroft,
    # hey_rhasspy) or a path to a custom .onnx/.tflite model.
    # google: the phrase to substring-match.
    wake_word: str = Field("hey_jarvis", alias="WAKE_WORD")
    wake_word_threshold: float = Field(0.5, alias="WAKE_WORD_THRESHOLD")
    wake_word_cooldown_seconds: float = Field(2.0, alias="WAKE_WORD_COOLDOWN_SECONDS")
    trigger_voice_url: str = Field(
        "http://localhost:2024/trigger_voice", alias="TRIGGER_VOICE_URL"
    )

    # --- External services ---
    tavily_api_key: str = Field("", alias="TAVILY_API_KEY")
    swiggy_food_mcp_url: str = Field("https://mcp.swiggy.com/food", alias="SWIGGY_FOOD_MCP_URL")
    swiggy_access_token: str = Field("", alias="SWIGGY_ACCESS_TOKEN")
    mcp_load_timeout_seconds: int = Field(10, alias="MCP_LOAD_TIMEOUT_SECONDS")

    @field_validator("llm_provider", "vision_llm_provider", mode="before")
    @classmethod
    def _normalize_provider(cls, v):
        # pi5-style spelling accepted as an alias.
        return "llama_cpp" if v == "llamacpp" else v

    @property
    def llm_slots(self) -> dict[str, int]:
        """Parsed LLM_SLOTS; malformed JSON degrades to no pinning."""
        try:
            slots = json.loads(self.llm_slots_json)
            if isinstance(slots, dict):
                return {k: int(v) for k, v in slots.items() if int(v) >= 0}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return {}

    @property
    def agent_llm_overrides(self) -> dict[str, dict]:
        """Parsed AGENT_LLM_OVERRIDES; malformed JSON degrades to no overrides."""
        try:
            overrides = json.loads(self.agent_llm_overrides_json)
            if isinstance(overrides, dict):
                return {k: v for k, v in overrides.items() if isinstance(v, dict)}
        except (json.JSONDecodeError, TypeError):
            pass
        return {}

    @property
    def music_stations(self) -> list[dict]:
        """Parsed MUSIC_STATIONS; malformed JSON degrades to an empty list."""
        try:
            stations = json.loads(self.music_stations_json)
            if isinstance(stations, list):
                return [s for s in stations if isinstance(s, dict) and s.get("name") and s.get("url")]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    @property
    def embedding_dim(self) -> int:
        if self.embedding_dim_override:
            return self.embedding_dim_override
        return _EMBEDDING_DIMS[self.embedding_provider]

    # Dim-suffixed collection names — the only names the rest of the app uses.
    @property
    def documents_collection(self) -> str:
        return f"{self.documents_collection_name}_{self.embedding_dim}"

    @property
    def history_collection(self) -> str:
        return f"{self.history_collection_name}_{self.embedding_dim}"

    @property
    def search_cache_collection(self) -> str:
        return f"{self.search_cache_collection_name}_{self.embedding_dim}"

    @property
    def mem0_collection(self) -> str:
        return f"{self.mem0_collection_name}_{self.embedding_dim}"

    @property
    def embedding_model(self) -> str:
        if self.embedding_provider == "openai":
            return self.openai_embedding_model
        return self.ollama_embedding_model

    @model_validator(mode="after")
    def _warn_insecure_prod(self) -> "Settings":
        if not self.auth_disabled and self.jwt_secret == "change-me-in-production":
            raise ValueError("AUTH_DISABLED=false requires a real JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
