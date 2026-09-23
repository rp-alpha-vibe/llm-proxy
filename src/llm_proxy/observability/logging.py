import json
import logging
import uuid
from dataclasses import dataclass

_LOGGER = logging.getLogger("llm_proxy.process")


@dataclass
class ProcessObservation:
    payload_chars: int | None
    token_count: int
    consumer: str | None = None
    operation: str = "rejected"
    pii_types: tuple[str, ...] = ()
    pii_count: int = 0
    pii_type_counts: tuple[tuple[str, int], ...] = ()
    fresh_detection: bool = False
    detect_ms: float = 0.0
    redis_ms: float = 0.0


def log_process_completion(
    *,
    status: int,
    latency_ms: float,
    observation: ProcessObservation | None,
) -> None:
    observed = observation or ProcessObservation(payload_chars=None, token_count=0)
    payload = {
        "event": "process_completed",
        "request_id": uuid.uuid4().hex,
        "consumer": observed.consumer,
        "operation": observed.operation,
        "status": status,
        "payload_chars": observed.payload_chars,
        "token_count": observed.token_count,
        "pii_types": list(observed.pii_types),
        "pii_count": observed.pii_count,
        "latency_ms": round(latency_ms, 3),
        "stages": {
            "detect_ms": round(observed.detect_ms, 3),
            "redis_ms": round(observed.redis_ms, 3),
            "total_ms": round(latency_ms, 3),
        },
    }
    _LOGGER.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
