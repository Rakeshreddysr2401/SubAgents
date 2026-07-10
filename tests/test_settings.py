"""Settings sanity: defaults, embedding-dim derivation, prod guard."""

import pytest


def test_defaults(settings):
    assert settings.llm_provider == "llama_cpp"
    assert settings.max_agent_visits == 3
    assert settings.postgres_dsn.startswith("postgresql://")


def test_embedding_dim_follows_provider(monkeypatch):
    from src.configs.settings import Settings

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    assert Settings().embedding_dim == 1536
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    assert Settings().embedding_dim == 768
    monkeypatch.setenv("EMBEDDING_DIM", "3072")
    assert Settings().embedding_dim == 3072


def test_local_by_default(monkeypatch):
    """Zero-key install: embeddings + Mem0 extraction must not require OpenAI."""
    from src.configs.settings import Settings

    # load_dotenv() at settings import copies the dev .env into os.environ, so
    # clear everything relevant — this tests the SHIPPED defaults.
    for var in ("EMBEDDING_PROVIDER", "MEM0_LLM_PROVIDER", "LLAMA_CPP_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.embedding_provider == "ollama"
    assert s.mem0_llm_provider == "main"
    assert "singireddys" not in s.llama_cpp_base_url  # no personal-host default


def test_collections_are_dim_suffixed(monkeypatch):
    from src.configs.settings import Settings

    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    s = Settings()
    assert s.documents_collection == "documents_768"
    assert s.history_collection == "history_768"
    assert s.search_cache_collection == "search_cache_768"
    assert s.mem0_collection == "mem0_memories_768"

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    s = Settings()
    assert s.documents_collection == "documents_1536"
    assert s.mem0_collection == "mem0_memories_1536"


def test_mem0_llm_config_follows_main_provider(monkeypatch):
    from src.configs.settings import get_settings
    from src.memory.mem0_client import _mem0_llm_config

    monkeypatch.setenv("MEM0_LLM_PROVIDER", "main")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "gemma4")
    get_settings.cache_clear()
    cfg = _mem0_llm_config()
    assert cfg["provider"] == "ollama"
    assert cfg["config"]["model"] == "gemma4"

    monkeypatch.setenv("LLM_PROVIDER", "llama_cpp")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llm-server:8080/v1")
    get_settings.cache_clear()
    cfg = _mem0_llm_config()
    assert cfg["provider"] == "openai"  # OpenAI-compatible endpoint trick
    assert cfg["config"]["openai_base_url"] == "http://llm-server:8080/v1"

    monkeypatch.setenv("MEM0_LLM_PROVIDER", "openai")  # explicit upgrade
    monkeypatch.setenv("MEM0_LLM_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    cfg = _mem0_llm_config()
    assert cfg == {"provider": "openai", "config": {"model": "gpt-4o-mini"}}
    get_settings.cache_clear()


def test_auth_enabled_requires_real_secret(monkeypatch):
    from src.configs.settings import Settings

    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    with pytest.raises(Exception, match="JWT_SECRET"):
        Settings()
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    assert Settings().auth_disabled is False
