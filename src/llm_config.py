# llm_config.py

import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# llama.cpp server — change if using Unsloth Studio (8888) or a remote machine
LLAMA_BASE_URL = os.getenv("LLAMA_BASE_URL", "http://localhost:8080/v1")

MODEL_NAME = os.getenv("SUPERVISOR_MODEL", "gemma")

# Vision model endpoint — defaults to same llama.cpp server as the chat model.
# Override VISION_BASE_URL in .env to route vision to a separate machine.
VISION_BASE_URL = os.getenv("VISION_BASE_URL", LLAMA_BASE_URL)
VISION_MODEL_NAME = os.getenv("VISION_MODEL", MODEL_NAME)


def get_llm(temperature: float = 0, enable_thinking: bool = False):
    return ChatOpenAI(
        base_url=LLAMA_BASE_URL,
        api_key="not-needed",
        model=MODEL_NAME,
        temperature=temperature,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        }
    )


# Default LLM (fast mode, no thinking overhead)
llm = get_llm(enable_thinking=False)