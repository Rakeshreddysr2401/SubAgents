# llm_config.py

from langchain.chat_models import init_chat_model as init_openai_model
from dotenv import load_dotenv

load_dotenv()

MAC = "192.168.1.22:11434"  # your Mac Mini IP
OLLAMA_BASE_URL  = "http://127.0.0.1:11434"  # your  local ollama
# Provider-Model registry
PROVIDER_REGISTRY = {
    "openai": {
        "gpt-4o": lambda temperature: init_openai_model("gpt-4o", temperature=temperature),
        "gpt-4-turbo": lambda temperature: init_openai_model("gpt-4-turbo", temperature=temperature),
        "gpt-3.5-turbo": lambda temperature: init_openai_model("gpt-3.5-turbo", temperature=temperature),
        "gpt-4o-mini": lambda temperature: init_openai_model("gpt-4o-mini", temperature=temperature)
    },

}


def get_llm(provider: str = "openai", model: str = "gpt-4o-mini", temperature: float = 0):
    provider_models = PROVIDER_REGISTRY.get(provider)
    if not provider_models:
        raise ValueError(f"Unsupported provider: {provider}")

    model_loader = provider_models.get(model)
    if not model_loader:
        raise ValueError(f"Unsupported model '{model}' for provider '{provider}'")

    return model_loader(temperature)

llm = get_llm()



# llm = get_llm(provider="ollama", model="phi3:mini", temperature=0)
# llm_with_tools = initialize_agent(
#     tools=get_tools(),
#     llm=llm,
#     agent=AgentType.OPENAI_FUNCTIONS,  # Simulates tool calling
#     verbose=True
# )

