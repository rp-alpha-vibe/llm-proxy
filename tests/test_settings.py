from pytest import MonkeyPatch

from llm_proxy.settings import Settings


def test_settings_defaults_are_safe_for_local_startup() -> None:
    settings = Settings.model_validate({})

    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.session_ttl_seconds == 900
    assert settings.post_demask_ttl_seconds == 120
    assert settings.max_concurrency == 100
    assert settings.config_path == type(settings).model_fields["config_path"].default


def test_settings_read_prefixed_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROXY_REDIS_URL", "redis://redis:6380/3")
    monkeypatch.setenv("LLM_PROXY_SESSION_TTL_SECONDS", "42")
    monkeypatch.setenv("LLM_PROXY_ENCRYPTION_KEY", "synthetic-test-key")

    settings = Settings.model_validate({})

    assert settings.redis_url == "redis://redis:6380/3"
    assert settings.session_ttl_seconds == 42
    assert settings.encryption_key is not None
    assert settings.encryption_key.get_secret_value() == "synthetic-test-key"
