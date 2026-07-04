"""LLM factories.

get_llm()          — main chat/agent model (llama.cpp or OpenAI per settings)
get_utility_llm()  — small/cheap model for background work: turn summaries,
                     frame descriptions, Mem0-style extraction.
"""

from langchain_openai import ChatOpenAI

from src.configs.settings import get_settings


def get_llm(temperature: float = 0) -> ChatOpenAI:
    s = get_settings()
    if s.llm_provider == "openai":
        return ChatOpenAI(model=s.openai_model, temperature=temperature)
    # llama.cpp / Ollama — any OpenAI-compatible server
    return ChatOpenAI(
        base_url=s.llama_cpp_base_url,
        api_key="not-needed",
        model=s.model_name,
        temperature=temperature,
    )


def get_utility_llm(temperature: float = 0) -> ChatOpenAI:
    s = get_settings()
    if s.llm_provider == "openai":
        return ChatOpenAI(model=s.utility_model, temperature=temperature)
    return ChatOpenAI(
        base_url=s.llama_cpp_base_url,
        api_key="not-needed",
        model=s.model_name,
        temperature=temperature,
    )
