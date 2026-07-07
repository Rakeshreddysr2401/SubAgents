"""LLM factories.

get_llm()          — main chat/agent model (llama.cpp or OpenAI per settings)
get_utility_llm()  — small/cheap model for background work: turn summaries,
                     frame descriptions, Mem0-style extraction.
get_vision_llm()   — the multimodal model for image analysis (guardian mode).
                     Always the llama.cpp VLM endpoint (the mac-mini) unless
                     the whole stack runs on OpenAI, so vision keeps working
                     even when the chat model is a text-only local model.
"""

from langchain_openai import ChatOpenAI

from src.configs.settings import get_settings


def get_vision_llm(temperature: float = 0) -> ChatOpenAI:
    s = get_settings()
    base_url = s.vision_llm_base_url or s.llama_cpp_base_url
    if s.llm_provider == "openai" and not s.vision_llm_base_url:
        # Full-OpenAI stack with no dedicated VLM configured — the main
        # OpenAI model is multimodal anyway.
        return ChatOpenAI(model=s.openai_model, temperature=temperature)
    return ChatOpenAI(
        base_url=base_url,
        api_key="not-needed",
        model=s.vision_model or s.model_name,
        temperature=temperature,
    )


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
