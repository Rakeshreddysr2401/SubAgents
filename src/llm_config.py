# llm_config.py

import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# Using llama.cpp server on the Mac Mini
LLAMA_CPP_BASE_URL = os.getenv("LLAMA_CPP_BASE_URL", "http://singireddys-mac-mini.local:8080/v1")
# The model name here depends on what is loaded in the llama-server
MODEL_NAME = os.getenv("SUPERVISOR_MODEL", "multimodal-model")

def get_llm(temperature: float = 0):
    # llama.cpp's server is OpenAI-compatible
    return ChatOpenAI(
        base_url=LLAMA_CPP_BASE_URL,
        api_key="not-needed",
        model=MODEL_NAME,
        temperature=temperature,
    )

# Default LLM
llm = get_llm()
