import asyncio
from collections.abc import Collection, Sequence

import pytest
from pydantic import ValidationError

from llm_proxy.application.process_service import (
    DemaskNotAllowedError,
    ProcessOutcome,
    ProcessService,
    SessionStateError,
)
from llm_proxy.detection.models import Detection, Detector, PiiType
from llm_proxy.masking.base import MaskContext, MaskedEntity, MaskResult, MaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore, make_session_key

SINGLE_PERSON = "synthetic-name"
SINGLE_EMAIL = "synthetic-email"
TWO_ENTITIES = "synthetic-name synthetic-email"


class StubDetector(Detector):
    def __init__(self) -> None:
        self.calls = 0

    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        self.calls += 1
        detections: list[Detection] = []
        values = (
            (PiiType.PERSON, "synthetic-name"),
            (PiiType.EMAIL, "synthetic-email"),
        )
        for pii_type, value in values:
            if pii_type not in enabled_types:
                continue
            start = text.find(value)
            if start < 0:
                continue
            detections.append(
                Detection(
                    type=pii_type,
                    start=start,
                    end=start + len(value),
                    confidence=1.0,
                    detector_id="synthetic-stub",
                )
            )
        return detections


class StubMaskStrategy(MaskStrategy):
    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult:
        ordered = sorted(detections, key=lambda detection: detection.start)
        entities: list[MaskedEntity] = []
        masked = text

        for index, detection in enumerate(ordered, start=1):
            rendered_mask = f"[[PII:{detection.type.value.upper()}:{index}]]"
            entity = MaskedEntity(
                type=detection.type,
                original_start=detection.start,
                original_end=detection.end,
                rendered_mask=rendered_mask,
                stable_entity_id=f"{detection.type.value}-{index}",
            )
            entities.append(entity)

        for detection in reversed(ordered):
            masked = (
                masked[: detection.start]
                + next(
                    entity.rendered_mask
                    for entity in entities
                    if entity.original_start == detection.start
                )
                + masked[detection.end :]
            )

        return MaskResult(text=masked, entities=tuple(entities))


class MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}
        self.ttls: dict[str, int] = {}

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
        self.ttls[key] = ttl_seconds
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        if key not in self.records:
            return False
        self.ttls[key] = ttl_seconds
        return True

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


class FailingStateStore(StateStore):
    async def get(self, key: str) -> SessionRecord | None:
        raise ConnectionError("synthetic state outage")

    async def create_if_absent(
        self,
        key: str,
        record: SessionRecord,
        ttl_seconds: int,
    ) -> bool:
        raise ConnectionError("synthetic state outage")

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        raise ConnectionError("synthetic state outage")

    async def delete(self, key: str) -> bool:
        raise ConnectionError("synthetic state outage")


class FailingCreateStateStore(MemoryStateStore):
    async def create_if_absent(
        self,
        key: str,
        record: SessionRecord,
        ttl_seconds: int,
    ) -> bool:
        raise ConnectionError("synthetic create outage")


class FailingTTLStateStore(MemoryStateStore):
    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        return False


def make_policy(
    system_id: str,
    *,
    policy_id: str | None = None,
    allow_demask: bool = True,
) -> ConsumerPolicy:
    return ConsumerPolicy(
        policy_id=policy_id or f"policy-{system_id}",
        system_id=system_id,
        enabled=True,
        pii_types=(PiiType.PERSON, PiiType.EMAIL),
        allow_demask=allow_demask,
        mask_strategy="placeholder",
    )


def make_context(policy: ConsumerPolicy) -> ConsumerContext:
    return ConsumerContext(consumer_id=policy.system_id, policy=policy)


def make_service(store: StateStore) -> tuple[ProcessService, StubDetector]:
    detector = StubDetector()
    service = ProcessService(
        state_store=store,
        detector=detector,
        mask_strategy=StubMaskStrategy(),
        session_ttl_seconds=900,
        post_demask_ttl_seconds=120,
    )
    return service, detector


@pytest.mark.asyncio
async def test_new_payload_then_retry_original_returns_same_mask() -> None:
    service, detector = make_service(MemoryStateStore())
    context = make_context(make_policy("consumer-1"))

    first = await service.process(context, "payload-1", SINGLE_PERSON)
    retry = await service.process(context, "payload-1", SINGLE_PERSON)

    assert first.outcome is ProcessOutcome.MASKED
    assert retry.outcome is ProcessOutcome.MASKED
    assert retry.result == first.result == "[[PII:PERSON:1]]"
    assert detector.calls == 1


@pytest.mark.asyncio
async def test_exact_mask_returns_original_and_shortens_ttl() -> None:
    store = MemoryStateStore()
    service, _ = make_service(store)
    context = make_context(make_policy("consumer-1"))

    masked = await service.process(context, "payload-1", SINGLE_PERSON)
    unmasked = await service.process(context, "payload-1", masked.result)
    key = make_session_key("consumer-1", "payload-1")

    assert unmasked.outcome is ProcessOutcome.EXACT_UNMASKED
    assert unmasked.result == SINGLE_PERSON
    assert store.ttls[key] == 120


@pytest.mark.asyncio
async def test_product_demask_preserves_text_and_repeats_known_masks() -> None:
    service, _ = make_service(MemoryStateStore())
    context = make_context(make_policy("consumer-1"))

    await service.process(context, "payload-1", TWO_ENTITIES)
    response = (
        "copy [[PII:EMAIL:2]]; person [[PII:PERSON:1]]; "
        "repeat [[PII:EMAIL:2]]; unknown [[PII:UNKNOWN:9]]"
    )

    result = await service.process(context, "payload-1", response)

    assert result.outcome is ProcessOutcome.PRODUCT_DEMASKED
    assert result.result == (
        "copy synthetic-email; person synthetic-name; "
        "repeat synthetic-email; unknown [[PII:UNKNOWN:9]]"
    )


@pytest.mark.asyncio
async def test_disabled_demask_rejects_exact_and_product_paths() -> None:
    service, _ = make_service(MemoryStateStore())
    context = make_context(make_policy("consumer-1", allow_demask=False))

    masked = await service.process(context, "payload-1", SINGLE_PERSON)

    with pytest.raises(DemaskNotAllowedError):
        await service.process(context, "payload-1", masked.result)
    with pytest.raises(DemaskNotAllowedError):
        await service.process(context, "payload-1", "modified response")


@pytest.mark.asyncio
async def test_consumer_and_session_isolation_prevents_mapping_disclosure() -> None:
    store = MemoryStateStore()
    service, _ = make_service(store)
    first_policy = make_policy("consumer-a", policy_id="policy-a")
    second_policy = make_policy("consumer-b", policy_id="policy-b")
    first_context = make_context(first_policy)
    second_context = make_context(second_policy)

    first_mask = await service.process(first_context, "shared-payload", SINGLE_PERSON)
    second_mask = await service.process(second_context, "shared-payload", SINGLE_EMAIL)
    foreign_result = await service.process(second_context, "shared-payload", first_mask.result)

    assert first_mask.result != second_mask.result
    assert "synthetic-name" not in foreign_result.result
    assert first_mask.result in foreign_result.result


@pytest.mark.asyncio
async def test_concurrent_duplicate_returns_one_consistent_mask() -> None:
    store = MemoryStateStore()
    service, _ = make_service(store)
    context = make_context(make_policy("consumer-1"))

    results = await asyncio.gather(
        service.process(context, "payload-1", SINGLE_PERSON),
        service.process(context, "payload-1", SINGLE_PERSON),
    )

    assert {result.outcome for result in results} == {ProcessOutcome.MASKED}
    assert {result.result for result in results} == {"[[PII:PERSON:1]]"}
    assert len(store.records) == 1


@pytest.mark.asyncio
async def test_state_outage_propagates_without_local_fallback() -> None:
    service, _ = make_service(FailingStateStore())
    context = make_context(make_policy("consumer-1"))

    with pytest.raises(ConnectionError):
        await service.process(context, "payload-1", SINGLE_PERSON)


@pytest.mark.asyncio
async def test_state_create_outage_propagates_without_local_fallback() -> None:
    service, _ = make_service(FailingCreateStateStore())
    context = make_context(make_policy("consumer-1"))

    with pytest.raises(ConnectionError):
        await service.process(context, "payload-1", SINGLE_PERSON)


@pytest.mark.asyncio
async def test_failed_ttl_shortening_is_a_state_failure() -> None:
    store = FailingTTLStateStore()
    service, _ = make_service(store)
    context = make_context(make_policy("consumer-1"))

    masked = await service.process(context, "payload-1", SINGLE_PERSON)

    with pytest.raises(SessionStateError):
        await service.process(context, "payload-1", masked.result)


@pytest.mark.asyncio
async def test_product_demask_supports_non_bracket_mask_strategy() -> None:
    store = MemoryStateStore()
    service, _ = make_service(store)
    context = make_context(make_policy("consumer-1"))
    key = make_session_key("consumer-1", "payload-1")
    record = SessionRecord(
        original_text=SINGLE_PERSON,
        masked_text="competition-mask",
        entities=(
            MaskedEntity(
                type=PiiType.PERSON,
                original_start=0,
                original_end=len(SINGLE_PERSON),
                rendered_mask="competition-mask",
                stable_entity_id="person-1",
            ),
        ),
        policy_id="policy-consumer-1",
        mask_strategy="competition",
    )
    store.records[key] = record

    result = await service.process(context, "payload-1", "prefix competition-mask suffix")

    assert result.outcome is ProcessOutcome.PRODUCT_DEMASKED
    assert result.result == f"prefix {SINGLE_PERSON} suffix"


@pytest.mark.asyncio
async def test_ambiguous_mask_mapping_is_left_unchanged() -> None:
    store = MemoryStateStore()
    service, _ = make_service(store)
    context = make_context(make_policy("consumer-1"))
    key = make_session_key("consumer-1", "payload-1")
    record = SessionRecord(
        original_text=TWO_ENTITIES,
        masked_text="stored-mask",
        entities=(
            MaskedEntity(
                type=PiiType.PERSON,
                original_start=0,
                original_end=len(SINGLE_PERSON),
                rendered_mask="[[PII:AMBIGUOUS:1]]",
                stable_entity_id="person-1",
            ),
            MaskedEntity(
                type=PiiType.EMAIL,
                original_start=len(SINGLE_PERSON) + 1,
                original_end=len(TWO_ENTITIES),
                rendered_mask="[[PII:AMBIGUOUS:1]]",
                stable_entity_id="email-1",
            ),
        ),
        policy_id="policy-consumer-1",
        mask_strategy="placeholder",
    )
    store.records[key] = record

    result = await service.process(context, "payload-1", "[[PII:AMBIGUOUS:1]]")

    assert result.outcome is ProcessOutcome.PRODUCT_DEMASKED
    assert result.result == "[[PII:AMBIGUOUS:1]]"


@pytest.mark.asyncio
async def test_foreign_policy_record_is_rejected() -> None:
    store = MemoryStateStore()
    service, _ = make_service(store)
    context = make_context(make_policy("consumer-1"))
    key = make_session_key("consumer-1", "payload-1")
    foreign_record = SessionRecord(
        original_text="foreign-original",
        masked_text="[[PII:PERSON:9]]",
        policy_id="policy-foreign",
        mask_strategy="placeholder",
    )
    store.records[key] = foreign_record

    with pytest.raises(SessionStateError):
        await service.process(context, "payload-1", "foreign-original")


def test_process_service_rejects_mismatched_consumer_context() -> None:
    policy = make_policy("consumer-1", policy_id="policy-1")
    with pytest.raises(ValidationError, match=r"consumer_id must match policy\.system_id"):
        ConsumerContext(consumer_id="consumer-2", policy=policy)
