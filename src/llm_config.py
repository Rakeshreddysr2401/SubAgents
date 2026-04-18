import os
from langchain.chat_models import init_chat_model as init_openai_model
from langchain_ollama import ChatOllama
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Override via SUPERVISOR_MODEL env var — useful for edge devices:
#   Laptop/desktop: gemma4:latest (default, best quality)
#   Jetson Nano / low RAM: SUPERVISOR_MODEL=llama3.2:3b
#   Mid-range edge: SUPERVISOR_MODEL=qwen2.5:7b
_SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", "gemma4:latest")

PROVIDER_REGISTRY = {
    "openai": {
        "gpt-4o":        lambda t: init_openai_model("gpt-4o",        temperature=t),
        "gpt-4-turbo":   lambda t: init_openai_model("gpt-4-turbo",   temperature=t),
        "gpt-3.5-turbo": lambda t: init_openai_model("gpt-3.5-turbo", temperature=t),
        "gpt-4o-mini":   lambda t: init_openai_model("gpt-4o-mini",   temperature=t),
    },
}


def get_llm():
    return ChatOllama(
        model=_SUPERVISOR_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )

llm = get_llm()
