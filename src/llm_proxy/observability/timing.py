from contextvars import ContextVar

_REDIS_SECONDS: ContextVar[list[float] | None] = ContextVar("llm_proxy_redis_seconds", default=None)


def start_redis_timing() -> None:
    _REDIS_SECONDS.set([0.0])


def add_redis_seconds(seconds: float) -> None:
    bucket = _REDIS_SECONDS.get()
    if bucket is not None:
        bucket[0] += seconds


def redis_seconds() -> float:
    bucket = _REDIS_SECONDS.get()
    return 0.0 if bucket is None else bucket[0]
