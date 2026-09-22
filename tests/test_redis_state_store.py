import asyncio
import hashlib
import time
from collections.abc import Callable

import pytest
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError

from llm_proxy.detection.models import PiiType
from llm_proxy.masking.base import MaskedEntity
from llm_proxy.state.crypto import SessionRecordCodec
from llm_proxy.state.models import SessionRecord
from llm_proxy.state.redis_store import RedisStateStore


class FakeRedis:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._values: dict[bytes, tuple[bytes, float | None]] = {}
        self.closed = False

    @staticmethod
    def _key(name: str | bytes) -> bytes:
        return name.encode("utf-8") if isinstance(name, str) else name

    def _discard_if_expired(self, key: bytes) -> None:
        entry = self._values.get(key)
        if entry is None:
            return
        _, expires_at = entry
        if expires_at is not None and self._clock() >= expires_at:
            self._values.pop(key, None)

    def peek(self, key: str) -> bytes | None:
        redis_key = self._key(key)
        self._discard_if_expired(redis_key)
        entry = self._values.get(redis_key)
        return None if entry is None else entry[0]

    def advance(self, seconds: float) -> None:
        current = self._clock()
        self._clock = lambda: current + seconds

    async def get(self, name: str | bytes) -> bytes | None:
        key = self._key(name)
        self._discard_if_expired(key)
        entry = self._values.get(key)
        return None if entry is None else entry[0]

    async def set(
        self,
        name: str | bytes,
        value: bytes,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        key = self._key(name)
        self._discard_if_expired(key)
        if nx and key in self._values:
            return False
        expires_at = None if ex is None else self._clock() + ex
        self._values[key] = (bytes(value), expires_at)
        return True

    async def expire(self, name: str | bytes, ttl_seconds: int) -> bool:
        key = self._key(name)
        self._discard_if_expired(key)
        if key not in self._values:
            return False
        self._values[key] = (self._values[key][0], self._clock() + ttl_seconds)
        return True

    async def delete(self, name: str | bytes) -> int:
        key = self._key(name)
        return int(self._values.pop(key, None) is not None)

    async def aclose(self) -> None:
        self.closed = True


class FailingRedis:
    async def get(self, name: str | bytes) -> bytes | None:
        raise RedisConnectionError("synthetic Redis outage")


def make_record(suffix: str = "one") -> SessionRecord:
    entity = MaskedEntity(
        type=PiiType.PERSON,
        original_start=0,
        original_end=13,
        rendered_mask=f"[[PII:PERSON:{suffix}]]",
        stable_entity_id=f"entity-{suffix}",
    )
    return SessionRecord(
        original_text=f"synthetic-name-{suffix}",
        masked_text=f"[[PII:PERSON:{suffix}]]",
        entities=(entity,),
        policy_id="policy-1",
        mask_strategy="placeholder",
    )


@pytest.mark.asyncio
async def test_redis_state_store_round_trip_and_key_scoping() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    fake = FakeRedis()
    store = RedisStateStore("redis://unused", codec, redis_client=fake)
    key = store.make_key("consumer-1", "payload-1")
    record = make_record()

    assert key == "session:consumer-1:" + hashlib.sha256(b"payload-1").hexdigest()
    assert await store.create_if_absent(key, record, 60) is True
    assert await store.get(key) == record
    assert await store.create_if_absent(key, make_record("two"), 60) is False
    assert await store.get(key) == record
    assert codec.decrypt(key, fake.peek(key) or b"") == record


@pytest.mark.asyncio
async def test_redis_state_store_concurrent_create_is_atomic() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    fake = FakeRedis()
    store = RedisStateStore("redis://unused", codec, redis_client=fake)
    key = store.make_key("consumer-1", "payload-1")
    records = (make_record("one"), make_record("two"))

    results = await asyncio.gather(
        store.create_if_absent(key, records[0], 60),
        store.create_if_absent(key, records[1], 60),
    )

    assert sorted(results) == [False, True]
    assert await store.get(key) in records


@pytest.mark.asyncio
async def test_redis_state_store_ttl_update_expiry_and_delete() -> None:
    now = 100.0
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    fake = FakeRedis(clock=lambda: now)
    store = RedisStateStore("redis://unused", codec, redis_client=fake)
    key = store.make_key("consumer-1", "payload-1")
    record = make_record()

    assert await store.create_if_absent(key, record, 60) is True
    assert await store.update_ttl(key, 30) is True
    assert await store.get(key) == record
    fake.advance(31)
    assert await store.get(key) is None

    assert await store.create_if_absent(key, record, 60) is True
    assert await store.delete(key) is True
    assert await store.get(key) is None


@pytest.mark.asyncio
async def test_redis_state_store_propagates_outage_without_local_fallback() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    store = RedisStateStore(
        "redis://unused",
        codec,
        redis_client=FailingRedis(),
    )

    with pytest.raises(RedisConnectionError):
        await store.get(store.make_key("consumer-1", "payload-1"))


@pytest.mark.asyncio
async def test_redis_state_store_rejects_blank_ids_and_non_positive_ttl() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    store = RedisStateStore("redis://unused", codec, redis_client=FakeRedis())

    with pytest.raises(ValueError):
        store.make_key(" ", "payload-1")
    with pytest.raises(ValueError):
        store.make_key("consumer-1", " ")
    with pytest.raises(ValueError):
        await store.create_if_absent(
            store.make_key("consumer-1", "payload-1"),
            make_record(),
            0,
        )


@pytest.mark.asyncio
async def test_redis_state_store_close_releases_client() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    fake = FakeRedis()
    store = RedisStateStore("redis://unused", codec, redis_client=fake)

    await store.close()

    assert fake.closed is True
