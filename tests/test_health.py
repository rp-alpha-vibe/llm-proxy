from fastapi.testclient import TestClient

from llm_proxy.main import create_app
from llm_proxy.settings import Settings


def test_healthz_returns_ok() -> None:
    settings = Settings.model_construct(
        redis_url="redis://example:6380/2",
        session_ttl_seconds=300,
    )
    client = TestClient(create_app(settings))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_exposes_resolved_settings() -> None:
    settings = Settings.model_validate({})
    application = create_app(settings)

    assert application.state.settings.redis_url == "redis://localhost:6379/0"
