from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "ollama": "llama3.1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./mrceo.db"
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM: "anthropic" or "ollama". A model name may override it with a prefix,
    # e.g. "ollama:qwen2.5" or "anthropic:claude-sonnet-5-5".
    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    manager_model: str = ""  # empty = provider default
    default_agent_model: str = ""  # used when an agent is created without a model

    @property
    def fake_mode(self) -> bool:
        """No LLM is called when Anthropic is the provider but has no key. Ollama needs none."""
        return self.llm_provider == "anthropic" and not self.anthropic_api_key

    @property
    def default_model(self) -> str:
        return _DEFAULT_MODELS.get(self.llm_provider, "")

    @property
    def resolved_manager_model(self) -> str:
        return self.manager_model or self.default_model

    @property
    def resolved_agent_model(self) -> str:
        return self.default_agent_model or self.default_model


settings = Settings()
