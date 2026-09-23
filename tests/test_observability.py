import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest, multiprocess

from llm_proxy.application.overload import ConcurrencyGate
from llm_proxy.application.process_service import (
    ProcessOutcome,
    ProcessResult,
    ProcessService,
)
from llm_proxy.application.stubs import SimpleEmailDetector, SimplePlaceholderMaskStrategy
from llm_proxy.main import create_app
from llm_proxy.observability.tokens import count_tokens
from llm_proxy.policies.consumer_resolver import ConfigConsumerResolver
from llm_proxy.policies.loader import YamlPolicyRegistry
from llm_proxy.policies.models import ConsumerContext
from llm_proxy.settings import Settings
from llm_proxy.state.models import SessionRecord, StateStore

_EMAIL = "synthetic@example.test"
_PAYLOAD_ID = "observability-payload-1"
_PAYLOAD = f"contact {_EMAIL}"


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


class _BlockingProcessService(ProcessService):
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def process(
        self,
        context: ConsumerContext,
        payload_id: str,
        payload: str,
    ) -> ProcessResult:
        del context, payload_id, payload
        self.entered.set()
        await self.release.wait()
        return ProcessResult("blocked-mask", ProcessOutcome.MASKED)


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return 0.0 if value is None else value


def _app(tmp_path: Path, *, limit: int = 10, service: ProcessService | None = None) -> FastAPI:
    config_path = tmp_path / "systems.yaml"
    config_path.write_text(
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: placeholder
""",
        encoding="utf-8",
    )
    if service is None:
        service = ProcessService(
            state_store=_MemoryStateStore(),
            detector=SimpleEmailDetector(),
            mask_strategy=SimplePlaceholderMaskStrategy(),
        )
    settings = Settings.model_validate(
        {
            "config_path": str(config_path),
            "default_consumer_id": "alfa_tester",
            "encryption_key": "0123456789abcdef0123456789abcdef",
            "max_concurrency": limit,
        }
    )
    return create_app(
        settings,
        process_service=service,
        consumer_resolver=ConfigConsumerResolver(YamlPolicyRegistry(config_path), "alfa_tester"),
        concurrency_gate=ConcurrencyGate(limit),
    )


def test_whitespace_tokenizer_counts_non_empty_pieces() -> None:
    assert count_tokens("") == 0
    assert count_tokens("   ") == 0
    assert count_tokens("alfa beta\tgamma") == 3


@pytest.mark.asyncio
async def test_process_emits_one_safe_completion_log_and_metrics(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app(tmp_path)
    before_requests = _sample("requests_total")
    before_detected = _sample("pii_detected_total", {"type": "email"})
    before_tokens = _sample("processed_tokens_total")

    with caplog.at_level(logging.INFO, logger="llm_proxy.process"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/process",
                json={"payload": _PAYLOAD, "payload_id": _PAYLOAD_ID},
            )
            metrics = await client.get("/metrics")

    assert response.status_code == 200
    events = [json.loads(record.getMessage()) for record in caplog.records]
    assert len(events) == 1
    event = events[0]
    assert event["event"] == "process_completed"
    assert event["operation"] == "mask"
    assert event["status"] == 200
    assert event["consumer"] == "alfa_tester"
    assert event["pii_types"] == ["email"]
    assert event["pii_count"] == 1
    assert event["token_count"] == 2
    assert event["payload_chars"] == len(_PAYLOAD)
    assert set(event["stages"]) == {"detect_ms", "redis_ms", "total_ms"}
    rendered = caplog.text
    assert _EMAIL not in rendered
    assert _PAYLOAD_ID not in rendered
    assert _sample("requests_total") == before_requests + 1
    assert _sample("responses_total", {"status": "200"}) >= 1
    assert _sample("pii_detected_total", {"type": "email"}) == before_detected + 1
    assert _sample("processed_tokens_total") == before_tokens + 2
    assert _sample("request_duration_seconds_count") >= before_requests + 1
    assert _EMAIL not in metrics.text
    assert _PAYLOAD_ID not in metrics.text
    assert "payload_id" not in metrics.text
    for name in (
        "requests_total",
        "responses_total",
        "requests_inflight",
        "request_duration_seconds",
        "pii_detected_total",
        "processed_tokens_total",
        "redis_duration_seconds",
        "overload_rejections_total",
    ):
        assert name in metrics.text


@pytest.mark.asyncio
async def test_retry_does_not_count_detection_again(tmp_path: Path) -> None:
    app = _app(tmp_path)
    before = _sample("pii_detected_total", {"type": "email"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/process",
            json={"payload": _PAYLOAD, "payload_id": _PAYLOAD_ID},
        )
        second = await client.post(
            "/process",
            json={"payload": _PAYLOAD, "payload_id": _PAYLOAD_ID},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert _sample("pii_detected_total", {"type": "email"}) == before + 1


@pytest.mark.asyncio
async def test_overload_and_invalid_request_do_not_log_payload(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    blocker = _BlockingProcessService()
    app = _app(tmp_path, limit=1, service=blocker)
    before_rejected = _sample("overload_rejections_total")

    with caplog.at_level(logging.INFO, logger="llm_proxy.process"):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            first = asyncio.create_task(
                client.post("/process", json={"payload": _PAYLOAD, "payload_id": _PAYLOAD_ID})
            )
            await blocker.entered.wait()
            overloaded = await client.post(
                "/process",
                json={"payload": _PAYLOAD, "payload_id": _PAYLOAD_ID},
            )
            invalid = await client.post(
                "/process",
                json={"payload": _PAYLOAD, "payload_id": _PAYLOAD_ID, "extra": _PAYLOAD},
            )
            blocker.release.set()
            await first

    assert overloaded.status_code == 429
    assert invalid.status_code == 422
    assert _sample("overload_rejections_total") == before_rejected + 1
    rendered = caplog.text
    assert _EMAIL not in rendered
    assert _PAYLOAD_ID not in rendered
    assert "Traceback" not in rendered
    statuses = {json.loads(record.getMessage())["status"] for record in caplog.records}
    assert {429, 422} <= statuses


def test_worker_metrics_aggregate_across_processes(tmp_path: Path) -> None:
    directory = tmp_path / "prometheus"
    directory.mkdir()
    env = os.environ.copy()
    env["PROMETHEUS_MULTIPROC_DIR"] = str(directory)
    env.pop("PYTEST_CURRENT_TEST", None)
    code = "\n".join(
        (
            "from llm_proxy.observability.metrics import pii_detected_total, requests_total",
            "import sys",
            "requests_total.inc(int(sys.argv[1]))",
            "pii_detected_total.labels(type='email').inc(int(sys.argv[2]))",
        )
    )
    for requests, detections in ((2, 1), (3, 4)):
        completed = subprocess.run(
            [sys.executable, "-c", code, str(requests), str(detections)],
            check=False,
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry, path=str(directory))
    rendered = generate_latest(registry).decode()
    assert registry.get_sample_value("requests_total") == 5
    assert registry.get_sample_value("pii_detected_total", {"type": "email"}) == 5
    assert _EMAIL not in rendered
    assert _PAYLOAD_ID not in rendered
