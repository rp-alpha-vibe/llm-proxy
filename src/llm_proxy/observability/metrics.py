import os
from collections.abc import Iterable

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
_REDIS_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)

requests_total = Counter("requests_total", "Accepted POST /process requests.")
responses_total = Counter("responses_total", "POST /process responses.", ["status"])
requests_inflight = Gauge(
    "requests_inflight",
    "In-flight POST /process requests.",
    multiprocess_mode="livesum",
)
request_duration_seconds = Histogram(
    "request_duration_seconds",
    "POST /process latency in seconds.",
    buckets=_LATENCY_BUCKETS,
)
pii_detected_total = Counter(
    "pii_detected_total",
    "PII entities found while creating a mask.",
    ["type"],
)
processed_tokens_total = Counter(
    "processed_tokens_total",
    "Input tokens counted by the whitespace tokenizer.",
)
redis_duration_seconds = Histogram(
    "redis_duration_seconds",
    "Redis call latency in seconds.",
    buckets=_REDIS_BUCKETS,
)
overload_rejections_total = Counter(
    "overload_rejections_total",
    "POST /process requests rejected because the process was overloaded.",
)


def render_metrics() -> bytes:
    directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if directory:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        payload = generate_latest(registry)
    else:
        payload = generate_latest()
    return bytes(payload)


def record_detection(type_counts: Iterable[tuple[str, int]]) -> None:
    for pii_type, count in type_counts:
        if count > 0:
            pii_detected_total.labels(type=pii_type).inc(count)
