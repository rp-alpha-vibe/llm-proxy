from collections.abc import Awaitable, Callable
from time import perf_counter

from starlette.requests import Request
from starlette.responses import Response

from llm_proxy.observability.logging import ProcessObservation, log_process_completion
from llm_proxy.observability.metrics import (
    overload_rejections_total,
    processed_tokens_total,
    record_detection,
    request_duration_seconds,
    requests_inflight,
    requests_total,
    responses_total,
)

_PROCESS_PATH = "/process"


async def observe_process(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.url.path != _PROCESS_PATH:
        return await call_next(request)

    requests_total.inc()
    requests_inflight.inc()
    started = perf_counter()
    try:
        response = await call_next(request)
    finally:
        requests_inflight.dec()

    latency_ms = (perf_counter() - started) * 1000
    observation = getattr(request.state, "process_observation", None)
    status = response.status_code
    responses_total.labels(status=str(status)).inc()
    request_duration_seconds.observe(latency_ms / 1000)
    if isinstance(observation, ProcessObservation):
        if observation.token_count > 0:
            processed_tokens_total.inc(observation.token_count)
        if observation.fresh_detection:
            record_detection(observation.pii_type_counts)
    if status == 429:
        overload_rejections_total.inc()
    log_process_completion(status=status, latency_ms=latency_ms, observation=observation)
    return response
