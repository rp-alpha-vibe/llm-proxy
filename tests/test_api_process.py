import asyncio
import os
from pathlib import Path

import httpx
import pytest
import redis.asyncio as redis
from fastapi import FastAPI
from redis.exceptions import RedisError

from llm_proxy.application.overload import ConcurrencyGate
from llm_proxy.application.process_service import (
    ProcessOutcome,
    ProcessResult,
    ProcessService,
)
from llm_proxy.application.stubs import SimpleEmailDetector, SimplePlaceholderMaskStrategy
from llm_proxy.main import create_app
from llm_proxy.policies.consumer_resolver import ConfigConsumerResolver
from llm_proxy.policies.loader import YamlPolicyRegistry
from llm_proxy.policies.models import ConsumerContext
from llm_proxy.settings import Settings
from llm_proxy.state.models import SessionRecord, StateStore, make_session_key


def write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class ApiMemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

    async def get(self, key: str) -> SessionRecord | None:
        return self.records.get(key)

    async def create_if_absent(
        self,
        key: str,
        record: SessionRecord,
        ttl_seconds: int,
    ) -> bool:
        if key in self.records:
            return False
        self.records[key] = record
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        return key in self.records

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


class FailingApiStateStore(ApiMemoryStateStore):
    async def get(self, key: str) -> SessionRecord | None:
        raise ConnectionError("synthetic state outage")


def make_service() -> tuple[ProcessService, ApiMemoryStateStore]:
    store = ApiMemoryStateStore()
    service = ProcessService(
        state_store=store,
        detector=SimpleEmailDetector(),
        mask_strategy=SimplePlaceholderMaskStrategy(),
    )
    return service, store


def make_settings(
    config_path: Path,
    *,
    default_consumer_id: str = "alfa_tester",
    encryption_key: str | None = "0123456789abcdef0123456789abcdef",
    max_concurrency: int = 10,
    redis_url: str | None = None,
) -> Settings:
    values: dict[str, object] = {
        "config_path": str(config_path),
        "default_consumer_id": default_consumer_id,
        "max_concurrency": max_concurrency,
    }
    if redis_url is not None:
        values["redis_url"] = redis_url
    if encryption_key is not None:
        values["encryption_key"] = encryption_key
    return Settings.model_validate(values)


def make_resolver(config_path: Path, default_consumer_id: str) -> ConfigConsumerResolver:
    return ConfigConsumerResolver(YamlPolicyRegistry(config_path), default_consumer_id)


def make_app(
    config_path: Path,
    *,
    default_consumer_id: str = "alfa_tester",
    service: ProcessService | None = None,
    max_concurrency: int = 10,
    encryption_key: str | None = "0123456789abcdef0123456789abcdef",
) -> tuple[FastAPI, ApiMemoryStateStore | None]:
    if service is not None:
        resolved_service = service
        store = None
    elif encryption_key is None:
        resolved_service = None
        store = None
    else:
        resolved_service, store = make_service()
    settings = make_settings(
        config_path,
        default_consumer_id=default_consumer_id,
        max_concurrency=max_concurrency,
        encryption_key=encryption_key,
    )
    app = create_app(
        settings,
        process_service=resolved_service,
        consumer_resolver=make_resolver(config_path, default_consumer_id),
        concurrency_gate=ConcurrencyGate(max_concurrency),
    )
    return app, store


class BlockingProcessService(ProcessService):
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def process(
        self,
        context: ConsumerContext,
        payload_id: str,
        payload: str,
    ) -> ProcessResult:
        self.entered.set()
        await self.release.wait()
        return ProcessResult("blocked-mask", ProcessOutcome.MASKED)


class FailingProcessService(ProcessService):
    def __init__(self) -> None:
        pass

    async def process(
        self,
        context: ConsumerContext,
        payload_id: str,
        payload: str,
    ) -> ProcessResult:
        raise RuntimeError("synthetic internal detail")


@pytest.mark.asyncio
async def test_http_mask_unmask_flow_uses_strict_result_contract(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            json={
                "payload": "contact synthetic@example.test",
                "payload_id": "payload-1",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"result": "contact [[PII:EMAIL:1]]"}
    masked = response.json()["result"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        retry = await client.post(
            "/process",
            json={
                "payload": "contact synthetic@example.test",
                "payload_id": "payload-1",
            },
        )
        response = await client.post(
            "/process",
            json={"payload": masked, "payload_id": "payload-1"},
        )

    assert retry.status_code == 200
    assert retry.json() == {"result": masked}

    assert response.status_code == 200
    assert response.json() == {"result": "contact synthetic@example.test"}


@pytest.mark.asyncio
async def test_http_preserves_payload_id_without_trimming(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path)
    spaced_id = " payload-1 "
    plain_id = "payload-1"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        spaced = await client.post(
            "/process",
            json={"payload": "spaced synthetic@example.test", "payload_id": spaced_id},
        )
        plain = await client.post(
            "/process",
            json={"payload": "plain synthetic@example.test", "payload_id": plain_id},
        )
        spaced_unmask = await client.post(
            "/process",
            json={"payload": spaced.json()["result"], "payload_id": spaced_id},
        )

    assert spaced.status_code == 200
    assert plain.status_code == 200
    assert spaced.json()["result"] != plain.json()["result"]
    assert spaced_unmask.status_code == 200
    assert spaced_unmask.json() == {"result": "spaced synthetic@example.test"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected_detail"),
    [
        ({"payload_id": "payload-1"}, "invalid request"),
        ({"payload": "text"}, "invalid request"),
        ({"payload": "text", "payload_id": "payload-1", "extra": True}, "invalid request"),
        ({"payload": 10, "payload_id": "payload-1"}, "invalid request"),
        ({"payload": "   ", "payload_id": "payload-1"}, "invalid request"),
        ({"payload": "text", "payload_id": "   "}, "invalid request"),
    ],
)
async def test_http_validation_errors_are_bounded(
    tmp_path: Path,
    body: dict[str, object],
    expected_detail: str,
) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post("/process", json=body)

    assert response.status_code == 422
    assert response.json() == {"detail": expected_detail}
    assert "synthetic@example.test" not in response.text


@pytest.mark.asyncio
async def test_http_invalid_json_returns_bounded_error(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            content="{invalid-json",
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid request"}
    assert "invalid-json" not in response.text


@pytest.mark.asyncio
async def test_http_rejects_disabled_consumer_without_auth_header(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  disabled:
    enabled: false
    pii_types: all
    allow_demask: true
    mask_strategy: placeholder
""",
    )
    app, _ = make_app(config_path, default_consumer_id="disabled")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "consumer not allowed"}


@pytest.mark.asyncio
async def test_http_rejects_unknown_consumer(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path, default_consumer_id="missing")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "consumer not allowed"}


@pytest.mark.asyncio
async def test_http_policy_limits_enabled_pii_types(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  demo:
    enabled: true
    pii_types:
      - person
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path, default_consumer_id="demo")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert response.status_code == 200
    assert response.json() == {"result": "synthetic@example.test"}


@pytest.mark.asyncio
async def test_http_enforces_disabled_demask_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: false
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        masked = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )
        response = await client.post(
            "/process",
            json={"payload": masked.json()["result"], "payload_id": "payload-1"},
        )

    assert masked.status_code == 200
    assert response.status_code == 403
    assert response.json() == {"detail": "demask not allowed"}


@pytest.mark.asyncio
async def test_http_returns_503_when_encryption_key_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path, encryption_key=None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        health = await client.get("/healthz")
        response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert health.status_code == 200
    assert response.status_code == 503
    assert response.json() == {"detail": "state unavailable"}


@pytest.mark.asyncio
async def test_http_returns_503_when_state_store_is_unavailable(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    service = ProcessService(
        state_store=FailingApiStateStore(),
        detector=SimpleEmailDetector(),
        mask_strategy=SimplePlaceholderMaskStrategy(),
    )
    app, _ = make_app(config_path, service=service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "state unavailable"}


@pytest.mark.asyncio
async def test_http_internal_errors_are_bounded(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    app, _ = make_app(config_path, service=FailingProcessService())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert response.status_code == 500

    assert response.json() == {"detail": "internal error"}
    assert "synthetic internal detail" not in response.text


@pytest.mark.asyncio
async def test_http_overload_returns_429_with_retry_after(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    blocking_service = BlockingProcessService()
    app, _ = make_app(
        config_path,
        service=blocking_service,
        max_concurrency=1,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = asyncio.create_task(
            client.post(
                "/process",
                json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
            )
        )
        await blocking_service.entered.wait()
        second = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )
        sustained = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )
        blocking_service.release.set()
        first_response = await first
        retry_response = await client.post(
            "/process",
            json={"payload": "synthetic@example.test", "payload_id": "payload-1"},
        )

    assert second.status_code == 429
    assert second.headers["Retry-After"] == "1"
    assert sustained.status_code == 429
    assert first_response.status_code == 200
    assert retry_response.status_code == 200


def _redis_smoke_url() -> str:
    return os.environ.get("LLM_PROXY_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")


async def _redis_is_reachable(redis_url: str) -> bool:
    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
    )
    try:
        await client.ping()
    except (RedisError, OSError, TimeoutError):
        return False
    finally:
        await client.aclose()
    return True


@pytest.mark.asyncio
async def test_http_redis_mask_retry_and_exact_unmask(tmp_path: Path) -> None:
    redis_url = _redis_smoke_url()
    if not await _redis_is_reachable(redis_url):
        pytest.skip("Redis is not available for the HTTP smoke")

    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
""",
    )
    original = "contact synthetic@example.test"
    payload_id = "redis-smoke-1"
    redis_key = make_session_key("alfa_tester", payload_id)
    settings = make_settings(config_path, redis_url=redis_url)
    app = create_app(
        settings,
        consumer_resolver=make_resolver(config_path, "alfa_tester"),
    )
    service = app.state.process_service
    assert service is not None
    probe = redis.Redis.from_url(redis_url, decode_responses=False)
    try:
        await probe.delete(redis_key)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            masked_response = await client.post(
                "/process",
                json={"payload": original, "payload_id": payload_id},
            )
            assert masked_response.status_code == 200
            assert masked_response.json() == {"result": "contact <EMAIL_1>"}
            masked = masked_response.json()["result"]
            retry_response = await client.post(
                "/process",
                json={"payload": original, "payload_id": payload_id},
            )
            unmask_response = await client.post(
                "/process",
                json={"payload": masked, "payload_id": payload_id},
            )

        assert retry_response.status_code == 200
        assert retry_response.json() == {"result": masked}
        assert unmask_response.status_code == 200
        assert unmask_response.json() == {"result": original}

        stored = await probe.get(redis_key)
        assert isinstance(stored, bytes)
        assert original.encode() not in stored
        assert b"synthetic@example.test" not in stored
    finally:
        await probe.delete(redis_key)
        await probe.aclose()
        await service._state_store.close()


@pytest.mark.asyncio
async def test_http_policy_isolation_uses_consumer_scoped_session(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
  demo:
    enabled: true
    pii_types:
      - person
    allow_demask: true
    mask_strategy: competition
""",
    )
    shared_service, _ = make_service()
    first_app, _ = make_app(config_path, service=shared_service, default_consumer_id="alfa_tester")
    second_app, _ = make_app(config_path, service=shared_service, default_consumer_id="demo")

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=first_app),
            base_url="http://first",
        ) as first_client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=second_app),
            base_url="http://second",
        ) as second_client,
    ):
        second_warmup = await second_client.post(
            "/process",
            json={"payload": "second@example.test", "payload_id": "shared"},
        )
        assert second_warmup.status_code == 200
        assert second_warmup.json() == {"result": "second@example.test"}
        first_response = await first_client.post(
            "/process",
            json={"payload": "first@example.test", "payload_id": "shared"},
        )
        first_mask = first_response.json()["result"]
        second_response = await second_client.post(
            "/process",
            json={"payload": first_mask, "payload_id": "shared"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == {"result": first_mask}
    assert "first@example.test" not in second_response.text
