from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration from environment variables (defaults match docker-compose.yml)."""

    model_config = SettingsConfigDict(extra="ignore")

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    mail_from: str = "router@example.com"
    agent_timeout_s: float = 60.0
    health_timeout_s: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
