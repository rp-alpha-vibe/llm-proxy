from typing import Any, Final

import redis.asyncio as redis

from .crypto import SessionRecordCodec
from .models import SessionRecord, StateStore, make_session_key

_DEFAULT_SOCKET_TIMEOUT: Final = 1.0


class RedisStateStore(StateStore):
    def __init__(
        self,
        redis_url: str,
        codec: SessionRecordCodec,
        *,
        redis_client: Any | None = None,
        socket_timeout: float = _DEFAULT_SOCKET_TIMEOUT,
        socket_connect_timeout: float = _DEFAULT_SOCKET_TIMEOUT,
    ) -> None:
        if not redis_url.strip():
            raise ValueError("redis_url must not be blank")
        if socket_timeout <= 0 or socket_connect_timeout <= 0:
            raise ValueError("Redis timeouts must be positive")

        self._codec = codec
        self._redis = redis_client or redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
        )

    def __repr__(self) -> str:
        return "<RedisStateStore>"

    @staticmethod
    def make_key(consumer_id: str, payload_id: str) -> str:
        return make_session_key(consumer_id, payload_id)

    async def get(self, redis_key: str) -> SessionRecord | None:
        value = await self._redis.get(redis_key)
        if value is None:
            return None
        if isinstance(value, str):
            value = value.encode("utf-8")
        return self._codec.decrypt(redis_key, bytes(value))

    async def create_if_absent(
        self,
        redis_key: str,
        record: SessionRecord,
        ttl_seconds: int,
    ) -> bool:
        self._validate_ttl(ttl_seconds)
        payload = self._codec.encrypt(redis_key, record)
        result = await self._redis.set(redis_key, payload, ex=ttl_seconds, nx=True)
        return bool(result)

    async def update_ttl(self, redis_key: str, ttl_seconds: int) -> bool:
        self._validate_ttl(ttl_seconds)
        result = await self._redis.expire(redis_key, ttl_seconds)
        return bool(result)

    async def delete(self, redis_key: str) -> bool:
        result = await self._redis.delete(redis_key)
        return bool(result)

    async def close(self) -> None:
        await self._redis.aclose()

    @staticmethod
    def _validate_ttl(ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
