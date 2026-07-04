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


def test_auth_enabled_requires_real_secret(monkeypatch):
    from src.configs.settings import Settings

    monkeypatch.setenv("AUTH_DISABLED", "false")
    monkeypatch.setenv("JWT_SECRET", "change-me-in-production")
    with pytest.raises(Exception, match="JWT_SECRET"):
        Settings()
    monkeypatch.setenv("JWT_SECRET", "s3cret")
    assert Settings().auth_disabled is False
