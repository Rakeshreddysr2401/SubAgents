"""get_vision_llm(): dedicated VLM endpoint with sensible fallbacks."""

import pytest

from src.configs.llm import get_vision_llm
from src.configs.settings import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_to_llama_cpp_config(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama_cpp")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://mac-mini:8080/v1")
    monkeypatch.setenv("SUPERVISOR_MODEL", "gemma4")
    # Empty = "fall back to the llama_cpp config" (delenv wouldn't isolate us
    # from the .env file, which pydantic-settings reads directly).
    monkeypatch.setenv("VISION_LLM_BASE_URL", "")
    monkeypatch.setenv("VISION_MODEL", "")
    get_settings.cache_clear()

    llm = get_vision_llm()
    assert str(llm.openai_api_base) == "http://mac-mini:8080/v1"
    assert llm.model_name == "gemma4"


def test_dedicated_vision_endpoint_wins(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama_cpp")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("VISION_LLM_BASE_URL", "http://mac-mini:8080/v1")
    monkeypatch.setenv("VISION_MODEL", "vlm-model")
    get_settings.cache_clear()

    llm = get_vision_llm()
    assert str(llm.openai_api_base) == "http://mac-mini:8080/v1"
    assert llm.model_name == "vlm-model"


def test_vision_url_overrides_even_openai_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("VISION_LLM_BASE_URL", "http://mac-mini:8080/v1")
    monkeypatch.setenv("VISION_MODEL", "vlm-model")
    get_settings.cache_clear()

    llm = get_vision_llm()
    assert str(llm.openai_api_base) == "http://mac-mini:8080/v1"


def test_full_openai_stack_uses_openai_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("VISION_LLM_BASE_URL", "")
    monkeypatch.setenv("VISION_MODEL", "")
    get_settings.cache_clear()

    llm = get_vision_llm()
    assert llm.model_name == "gpt-4o"
