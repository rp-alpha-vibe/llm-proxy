from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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

    @field_validator("encryption_key", mode="before")
    @classmethod
    def empty_encryption_key_is_missing(
        cls,
        value: SecretStr | str | None,
    ) -> SecretStr | str | None:
        if value == "":
            return None
        return value

    post_demask_ttl_seconds: int = Field(default=120, gt=0)
    max_concurrency: int = Field(default=100, gt=0)
    config_path: Path = Path("config/systems.example.yaml")
    default_consumer_id: str = Field(default="alfa_tester", min_length=1)
    overload_retry_after_seconds: int = Field(default=1, ge=1, le=60)
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)


def get_settings() -> Settings:
    return Settings()


def require_encryption_key(settings: Settings) -> SecretStr:
    if settings.encryption_key is None:
        raise ValueError("encryption_key is required for stateful processing")
    return settings.encryption_key
