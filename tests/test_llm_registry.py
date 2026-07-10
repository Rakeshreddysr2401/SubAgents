"""build_chat_model / get_llm: provider switch, slot pinning, fallback config."""

import pytest
from langchain_openai import ChatOpenAI

from src.configs.llm import get_fallback_llm, get_llm, get_utility_llm
from src.configs.settings import get_settings
from src.services.llm_registry import build_chat_model, is_connection_error


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _local_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llama_cpp")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llm-server:8080/v1")
    monkeypatch.setenv("SUPERVISOR_MODEL", "gemma4")
    get_settings.cache_clear()


# ── provider switch ─────────────────────────────────────────────────────────

def test_llama_cpp_builds_openai_compatible_client(monkeypatch):
    _local_env(monkeypatch)
    llm = get_llm()
    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base) == "http://llm-server:8080/v1"
    assert llm.model_name == "gemma4"
    assert llm.max_retries == 0  # retries live in ResilientModelMiddleware


def test_llamacpp_spelling_accepted_as_alias(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "llamacpp")
    monkeypatch.setenv("LLAMA_CPP_BASE_URL", "http://llm-server:8080/v1")
    get_settings.cache_clear()
    assert get_settings().llm_provider == "llama_cpp"


def test_openai_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    get_settings.cache_clear()
    llm = get_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "gpt-4o-mini"


def test_anthropic_provider(monkeypatch):
    from langchain_anthropic import ChatAnthropic

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    llm = get_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-5"  # default when LLM_MODEL unset


def test_gemini_provider(monkeypatch):
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-2.5-pro")
    get_settings.cache_clear()
    llm = get_llm()
    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.model.endswith("gemini-2.5-pro")


def test_ollama_provider(monkeypatch):
    from langchain_ollama import ChatOllama

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "llama3.2")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    get_settings.cache_clear()
    llm = get_llm()
    assert isinstance(llm, ChatOllama)
    assert llm.model == "llama3.2"


def test_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        build_chat_model({"provider": "grok"})


# ── slot pinning ────────────────────────────────────────────────────────────

def test_agent_slot_pinned_for_llama_cpp(monkeypatch):
    _local_env(monkeypatch)
    monkeypatch.setenv(
        "LLM_SLOTS", '{"conversation": 0, "swiggy": 1, "tracker": 2, "planner": 3}'
    )
    get_settings.cache_clear()
    for agent, slot in [("conversation", 0), ("swiggy", 1), ("tracker", 2), ("planner", 3)]:
        llm = get_llm(agent)
        assert llm.extra_body == {"id_slot": slot}, agent


def test_no_slot_without_agent_name(monkeypatch):
    _local_env(monkeypatch)
    assert get_llm().extra_body is None


def test_no_slot_for_cloud_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_SLOTS", '{"conversation": 0}')
    get_settings.cache_clear()
    assert get_llm("conversation").extra_body is None


def test_malformed_slots_json_degrades_to_no_pin(monkeypatch):
    _local_env(monkeypatch)
    monkeypatch.setenv("LLM_SLOTS", "not-json")
    get_settings.cache_clear()
    assert get_llm("conversation").extra_body is None


# ── per-agent overrides ─────────────────────────────────────────────────────

def test_agent_override_switches_provider(monkeypatch):
    from langchain_ollama import ChatOllama

    _local_env(monkeypatch)
    monkeypatch.setenv(
        "AGENT_LLM_OVERRIDES",
        '{"planner": {"provider": "ollama", "model": "qwen3", "base_url": "http://localhost:11434"}}',
    )
    get_settings.cache_clear()
    planner_llm = get_llm("planner")
    assert isinstance(planner_llm, ChatOllama)
    assert planner_llm.model == "qwen3"
    # Other agents untouched.
    assert isinstance(get_llm("conversation"), ChatOpenAI)


# ── utility + fallback ──────────────────────────────────────────────────────

def test_utility_llm_uses_cheap_model_on_openai(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("UTILITY_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    get_settings.cache_clear()
    assert get_utility_llm().model_name == "gpt-4o-mini"


def test_fallback_none_when_unconfigured(monkeypatch):
    _local_env(monkeypatch)
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "")
    monkeypatch.setenv("FALLBACK_LLM_MODEL", "")
    get_settings.cache_clear()
    assert get_fallback_llm() is None


def test_fallback_built_without_slot(monkeypatch):
    _local_env(monkeypatch)
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "openai")
    monkeypatch.setenv("FALLBACK_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("FALLBACK_LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    fb = get_fallback_llm()
    assert isinstance(fb, ChatOpenAI)
    assert fb.extra_body is None


# ── error classification ────────────────────────────────────────────────────

def test_connection_errors_detected():
    import httpx

    assert is_connection_error(ConnectionError("refused"))
    assert is_connection_error(httpx.ConnectError("no route"))
    assert is_connection_error(TimeoutError("slow"))  # OSError subclass


def test_wrapped_cause_detected():
    outer = RuntimeError("wrapper")
    outer.__cause__ = ConnectionError("refused")
    assert is_connection_error(outer)


def test_request_errors_not_connection():
    assert not is_connection_error(ValueError("bad tool schema"))
    assert not is_connection_error(KeyError("missing"))
