from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./mrceo.db"
    anthropic_api_key: str | None = None
    manager_model: str = "claude-sonnet-5-5"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
