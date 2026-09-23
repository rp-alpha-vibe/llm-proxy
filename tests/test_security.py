import asyncio
import logging
import os
import subprocess
from collections.abc import Collection, Sequence
from pathlib import Path

import httpx
import pytest
import redis.asyncio as redis
from fastapi import FastAPI
from pydantic import SecretStr
from redis.exceptions import RedisError

from llm_proxy.application.process_service import ProcessService
from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import MANDATORY_PII_TYPES, Detection, Detector, PiiType
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.main import create_app
from llm_proxy.masking.placeholder import PlaceholderMaskStrategy
from llm_proxy.policies.consumer_resolver import ConfigConsumerResolver
from llm_proxy.policies.loader import YamlPolicyRegistry
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.settings import Settings
from llm_proxy.state.crypto import SessionRecordCodec
from llm_proxy.state.models import SessionRecord, StateStore, make_session_key
from llm_proxy.state.redis_store import RedisStateStore

_NAME = "Иван Петров"
_PHONE = "+7 900 111-22-33"
_EMAIL = "leak-check@example.test"
_PAN = "4111111111111111"
_PASSPORT = "45 12 654321"
_PAYLOAD_ID = "security-payload-1"
_SECRETS = (_NAME, _PHONE, _EMAIL, _PAN, _PASSPORT, _PAYLOAD_ID)
_ROOT = Path(__file__).resolve().parents[1]


class _MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

    async def get(self, key: str) -> SessionRecord | None:
        return self.records.get(key)

    async def create_if_absent(self, key: str, record: SessionRecord, ttl_seconds: int) -> bool:
        if key in self.records:
            return False
        self.records[key] = record
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        return key in self.records

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


class _CapturingRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, name: str) -> bytes | None:
        return self.values.get(name)

    async def set(
        self,
        name: str,
        value: bytes,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        del ex
        if nx and name in self.values:
            return False
        self.values[name] = bytes(value)
        return True

    async def expire(self, name: str, ttl_seconds: int) -> bool:
        del ttl_seconds
        return name in self.values

    async def delete(self, name: str) -> int:
        return int(self.values.pop(name, None) is not None)

    async def aclose(self) -> None:
        return None


class _ExplodingDetector:
    def detect(self, text: str, enabled_types: Collection[PiiType]) -> Sequence[Detection]:
        del enabled_types
        raise RuntimeError(text)


def _engine() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def _policy(system_id: str) -> ConsumerPolicy:
    return ConsumerPolicy(
        policy_id=f"policy-{system_id}",
        system_id=system_id,
        enabled=True,
        pii_types=MANDATORY_PII_TYPES,
        allow_demask=True,
        mask_strategy="placeholder",
    )


def _context(system_id: str) -> ConsumerContext:
    return ConsumerContext(consumer_id=system_id, policy=_policy(system_id))


def _service(store: StateStore, detector: Detector | None = None) -> ProcessService:
    return ProcessService(
        state_store=store,
        detector=detector if detector is not None else _engine(),
        mask_strategy=PlaceholderMaskStrategy(),
        session_ttl_seconds=30,
        post_demask_ttl_seconds=1,
    )


def _sensitive_payload() -> str:
    return f"клиент {_NAME}, тел. {_PHONE}, {_EMAIL}, карта {_PAN}, паспорт {_PASSPORT}"


def _assert_secrets_absent(text: str) -> None:
    for secret in _SECRETS:
        assert secret not in text


def _rendered_logs(caplog: pytest.LogCaptureFixture) -> str:
    chunks: list[str] = [caplog.text]
    for record in caplog.records:
        chunks.append(record.getMessage())
        chunks.append(str(record.args))
        if record.exc_info and record.exc_info[1] is not None:
            chunks.append(str(record.exc_info[1]))
    return "\n".join(chunks)


def _write_config(path: Path) -> None:
    path.write_text(
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: placeholder
""",
        encoding="utf-8",
    )


def _app(tmp_path: Path, service: ProcessService) -> FastAPI:
    config_path = tmp_path / "systems.yaml"
    _write_config(config_path)
    settings = Settings.model_validate(
        {
            "config_path": str(config_path),
            "default_consumer_id": "alfa_tester",
            "encryption_key": "0123456789abcdef0123456789abcdef",
        }
    )
    return create_app(
        settings,
        process_service=service,
        consumer_resolver=ConfigConsumerResolver(
            YamlPolicyRegistry(config_path),
            "alfa_tester",
        ),
    )


@pytest.mark.asyncio
async def test_process_logs_omit_synthetic_pii(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app(tmp_path, _service(_MemoryStateStore()))
    payload = _sensitive_payload()

    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/process",
                json={"payload": payload, "payload_id": _PAYLOAD_ID},
            )

    assert response.status_code == 200
    assert _EMAIL not in response.text
    _assert_secrets_absent(_rendered_logs(caplog))


@pytest.mark.asyncio
async def test_metrics_surface_omits_payload_and_pii(tmp_path: Path) -> None:
    app = _app(tmp_path, _service(_MemoryStateStore()))
    payload = _sensitive_payload()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        processed = await client.post(
            "/process",
            json={"payload": payload, "payload_id": _PAYLOAD_ID},
        )
        metrics = await client.get("/metrics")

    assert processed.status_code == 200
    _assert_secrets_absent(metrics.text)
    _assert_secrets_absent(str(metrics.headers))


@pytest.mark.asyncio
async def test_redis_value_and_key_do_not_contain_plaintext() -> None:
    client = _CapturingRedis()
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    store = RedisStateStore("redis://unused", codec, redis_client=client)
    payload = _sensitive_payload()

    result = await _service(store).process(_context("alfa_tester"), _PAYLOAD_ID, payload)

    assert _EMAIL not in result.result
    stored = next(iter(client.values.values()))
    key = next(iter(client.values))
    for secret in (_NAME, _PHONE, _EMAIL, _PAN, _PASSPORT, payload):
        assert secret.encode() not in stored
    assert _PAYLOAD_ID not in key
    assert "alfa_tester" in key


@pytest.mark.asyncio
async def test_other_consumer_and_payload_cannot_demask() -> None:
    service = _service(_MemoryStateStore())
    masked = await service.process(_context("consumer-a"), "payload-a", _sensitive_payload())

    other_consumer = await service.process(_context("consumer-b"), "payload-a", masked.result)
    other_payload = await service.process(_context("consumer-a"), "payload-b", masked.result)

    assert _EMAIL not in other_consumer.result
    assert _NAME not in other_consumer.result
    assert masked.result in other_consumer.result
    assert _EMAIL not in other_payload.result
    assert masked.result in other_payload.result


def test_encryption_key_comes_from_environment_and_real_env_is_untracked() -> None:
    gitignore = (_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert any(line.strip() == ".env" for line in gitignore.splitlines())
    example = (_ROOT / ".env.example").read_text(encoding="utf-8")
    key_lines = [
        line for line in example.splitlines() if line.startswith("LLM_PROXY_ENCRYPTION_KEY=")
    ]
    assert key_lines == ["LLM_PROXY_ENCRYPTION_KEY="]

    tracked = subprocess.check_output(
        ["git", "ls-files"],
        cwd=_ROOT,
        text=True,
        encoding="utf-8",
    ).splitlines()
    assert ".env" not in tracked
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=_ROOT,
        check=False,
    )
    assert ignored.returncode == 0

    for relative in tracked:
        path = _ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "LLM_PROXY_ENCRYPTION_KEY=" not in stripped:
                continue
            marker = "LLM_PROXY_ENCRYPTION_KEY="
            index = stripped.find(marker)
            prefix = stripped[:index].strip()
            if prefix not in {"", "export"}:
                continue
            value = stripped[index + len(marker) :].strip().strip("\"'")
            assert value in {"", "${LLM_PROXY_ENCRYPTION_KEY:-}"}


def test_settings_and_codec_repr_hide_encryption_key() -> None:
    settings = Settings.model_validate({"encryption_key": "0123456789abcdef0123456789abcdef"})
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))

    assert "0123456789abcdef0123456789abcdef" not in repr(settings)
    assert "0123456789abcdef0123456789abcdef" not in str(settings)
    assert repr(codec) == "<SessionRecordCodec>"


def _redis_url() -> str:
    return os.environ.get("LLM_PROXY_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")


async def _redis_reachable(redis_url: str) -> bool:
    client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.3, socket_timeout=0.3)
    try:
        await client.ping()
    except (RedisError, OSError, TimeoutError):
        return False
    finally:
        await client.aclose()
    return True


@pytest.mark.asyncio
async def test_real_redis_ttl_deletes_the_session() -> None:
    redis_url = _redis_url()
    if not await _redis_reachable(redis_url):
        pytest.skip("Redis is not available for TTL cleanup")

    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    store = RedisStateStore(redis_url, codec)
    key = make_session_key("security-ttl", "payload-ttl")
    record = SessionRecord(
        original_text="synthetic-ttl",
        masked_text="[[PII:EMAIL:1]]",
        entities=(),
        policy_id="policy-security-ttl",
        mask_strategy="placeholder",
    )
    try:
        await store.delete(key)
        assert await store.create_if_absent(key, record, 30) is True
        assert await store.update_ttl(key, 1) is True
        await asyncio.sleep(1.5)
        assert await store.get(key) is None
    finally:
        await store.delete(key)
        await store.close()


@pytest.mark.asyncio
async def test_error_responses_omit_pii_and_stack_traces(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app(tmp_path, _service(_MemoryStateStore(), _ExplodingDetector()))
    payload = _sensitive_payload()

    with caplog.at_level(logging.DEBUG):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            failed = await client.post(
                "/process",
                json={"payload": payload, "payload_id": _PAYLOAD_ID},
            )
            invalid = await client.post(
                "/process",
                json={"payload": payload, "payload_id": _PAYLOAD_ID, "extra": payload},
            )

    assert failed.status_code == 500
    assert failed.json() == {"detail": "internal error"}
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "invalid request"}
    combined = failed.text + invalid.text + _rendered_logs(caplog)
    _assert_secrets_absent(combined)
    assert "Traceback" not in combined
    assert "RuntimeError" not in combined


def test_deployment_does_not_terminate_tls_inside_the_process() -> None:
    main_source = (_ROOT / "src" / "llm_proxy" / "main.py").read_text(encoding="utf-8")
    dockerfile = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ssl" not in main_source.casefold()
    assert "ssl" not in dockerfile.casefold()
    assert "8000:8000" in compose
    assert "tls" not in compose.casefold()
