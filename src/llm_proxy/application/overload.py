import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class ConcurrencyLimitExceeded(RuntimeError):
    pass


class ConcurrencyGate:
    def __init__(self, limit: int, *, retry_after_seconds: int = 1) -> None:
        if limit <= 0:
            raise ValueError("concurrency limit must be positive")
        if retry_after_seconds <= 0:
            raise ValueError("retry_after_seconds must be positive")

        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        self._in_flight = 0
        self._lock = asyncio.Lock()

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._lock:
            if self._in_flight >= self.limit:
                raise ConcurrencyLimitExceeded()
            self._in_flight += 1
        try:
            yield
        finally:
            async with self._lock:
                self._in_flight -= 1
