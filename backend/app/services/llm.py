"""Chat-model factory. `spec` is "<model>" (uses LLM_PROVIDER) or "<provider>:<model>".

Only known provider prefixes are split off, because Ollama model names contain colons
themselves (e.g. "llama3.1:8b").
"""
from langchain_core.language_models import BaseChatModel

from ..config import settings

PROVIDERS = ("anthropic", "ollama")


def split_spec(spec: str) -> tuple[str, str]:
    provider, sep, name = spec.partition(":")
    if sep and provider in PROVIDERS:
        return provider, name
    return settings.llm_provider, spec


def make_model(spec: str) -> BaseChatModel:
    provider, name = split_spec(spec)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=name, base_url=settings.ollama_base_url)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        # pydantic-settings does not export .env to os.environ, so pass the key explicitly.
        return ChatAnthropic(model=name, api_key=settings.anthropic_api_key)
    raise ValueError(f"Unknown LLM provider {provider!r}; use one of {PROVIDERS}")
