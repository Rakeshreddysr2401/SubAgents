# llm_config.py

from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# 👉 Change this depending on how you're running
LLAMA_BASE_URL = "http://localhost:8080/v1"   # if using llama-server manually
# LLAMA_BASE_URL = "http://127.0.0.1:8888/v1"  # if using Unsloth Studio

MODEL_NAME = "gemma"  # name doesn't matter much for llama.cpp


def get_llm(temperature: float = 0, enable_thinking: bool = False):
    """
    Returns LLM with dynamic thinking control
    """

    return ChatOpenAI(
        base_url=LLAMA_BASE_URL,
        api_key="not-needed",
        model=MODEL_NAME,
        temperature=temperature,

        # 🔥 THIS is the key part
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": enable_thinking
            }
        }
    )


# Default LLM (fast mode)
llm = get_llm(enable_thinking=False)