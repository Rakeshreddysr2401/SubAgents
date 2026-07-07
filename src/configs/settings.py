"""Central application settings — single source of truth for all env config.

Every module should use `get_settings()` instead of scattered `os.getenv` calls.
Values load from the process environment first, then `.env`.
"""

from functools import lru_cache
from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic import Field, model_validator
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
    llm_provider: Literal["llama_cpp", "openai"] = Field("llama_cpp", alias="LLM_PROVIDER")
    llama_cpp_base_url: str = Field(
        "http://singireddys-mac-mini.local:8080/v1", alias="LLAMA_CPP_BASE_URL"
    )
    # Model name loaded in the llama.cpp server (legacy env name kept)
    model_name: str = Field("multimodal-model", alias="SUPERVISOR_MODEL")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    # Small/cheap model for background work: turn summaries, Mem0 extraction, frame descriptions
    utility_model: str = Field("gpt-4o-mini", alias="UTILITY_MODEL")
    # Dedicated vision (VLM) endpoint — the mac-mini llama.cpp server. Vision
    # consumers (guardian mode, frame analysis) always hit this, so the chat
    # model can run anywhere (local Ollama, OpenAI) without losing vision.
    # Empty values fall back to LLAMA_CPP_BASE_URL / SUPERVISOR_MODEL.
    vision_llm_base_url: str = Field("", alias="VISION_LLM_BASE_URL")
    vision_model: str = Field("", alias="VISION_MODEL")

    # --- Embeddings ---
    embedding_provider: Literal["openai", "ollama"] = Field("openai", alias="EMBEDDING_PROVIDER")
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
    mem0_llm_provider: Literal["openai", "llama_cpp"] = Field("openai", alias="MEM0_LLM_PROVIDER")
    mem0_llm_model: str = Field("gpt-4o-mini", alias="MEM0_LLM_MODEL")
    mem0_collection: str = Field("mem0_memories", alias="MEM0_COLLECTION")
    recall_limit: int = Field(5, alias="MEM0_RECALL_LIMIT")

    # --- RAG ---
    documents_collection: str = "documents"
    history_collection: str = "history"
    search_cache_collection: str = "search_cache"
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

    @property
    def music_stations(self) -> list[dict]:
        """Parsed MUSIC_STATIONS; malformed JSON degrades to an empty list."""
        import json

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
