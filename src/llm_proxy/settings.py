from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_PROXY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    redis_url: str = "redis://localhost:6379/0"
    encryption_key: SecretStr | None = None
    session_ttl_seconds: int = Field(default=900, gt=0)
    post_demask_ttl_seconds: int = Field(default=120, gt=0)
    max_concurrency: int = Field(default=100, gt=0)
    config_path: Path = Path("config/systems.example.yaml")
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)


def get_settings() -> Settings:
    return Settings()
