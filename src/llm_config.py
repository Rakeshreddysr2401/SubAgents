# llm_config.py

import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# Official OpenAI API Key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Disable vision capabilities if requested
DISABLE_VISION = os.getenv("DISABLE_VISION", "false").lower() == "true"

# Local llama.cpp / Ollama server - used if no OpenAI API key is found
LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL_NAME = os.getenv("SUPERVISOR_MODEL", "gpt-4o")

# Vision model endpoint
VISION_BASE_URL = os.getenv("VISION_BASE_URL", LLAMA_BASE_URL)
VISION_MODEL_NAME = os.getenv("VISION_MODEL", "llava")


def get_llm(temperature: float = 0, enable_thinking: bool = False):
    """
    Returns an LLM instance. 
    Prioritizes official OpenAI if API key is present.
    """
    if OPENAI_API_KEY:
        # Use official OpenAI
        return ChatOpenAI(
            model="gpt-4o",  # or gpt-4
            temperature=temperature,
            api_key=OPENAI_API_KEY,
            timeout=60.0
        )

    # Fallback to local Ollama / Llama.cpp (OpenAI-compatible)
    return ChatOpenAI(
        base_url=LLAMA_BASE_URL,
        api_key="not-needed",
        model=MODEL_NAME,
        temperature=temperature,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        } if enable_thinking else {}
    )


# Default LLM
llm = get_llm(enable_thinking=False)