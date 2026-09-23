from collections.abc import Collection

import pytest

from llm_proxy.application.process_service import (
    DemaskNotAllowedError,
    ProcessOutcome,
    ProcessService,
)
from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.masking.base import MaskedEntity, MaskStrategy
from llm_proxy.masking.competition import CompetitionMaskStrategy
from llm_proxy.masking.placeholder import PlaceholderMaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore, make_session_key

_PERSON = "Ivan Petrov"
_EMAIL_A = "demo@example.com"
_EMAIL_B = "other@example.com"
_PHONE = "+79001234567"
_ORIGINAL = f"{_PERSON}, {_EMAIL_A}, {_EMAIL_B}."
_REPEAT = f"{_PERSON} / {_PERSON}"
_VALUES = (
    (PiiType.PERSON, _PERSON),
    (PiiType.EMAIL, _EMAIL_A),
    (PiiType.EMAIL, _EMAIL_B),
    (PiiType.PHONE, _PHONE),
)


class MemoryStateStore(StateStore):
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


class LiteralDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> tuple[Detection, ...]:
        enabled = frozenset(enabled_types)
        found: list[Detection] = []
        for pii_type, value in _VALUES:
            if pii_type not in enabled:
                continue
            start = 0
            while True:
                index = text.find(value, start)
                if index < 0:
                    break
                found.append(
                    Detection(
                        type=pii_type,
                        start=index,
                        end=index + len(value),
                        confidence=1.0,
                        detector_id="fixture",
                    )
                )
                start = index + len(value)
        return tuple(found)


def _service(store: MemoryStateStore, strategy: MaskStrategy) -> ProcessService:
    return ProcessService(
        state_store=store,
        detector=LiteralDetector(),
        mask_strategy=strategy,
    )


def _context(
    system_id: str,
    strategy_name: str,
    *,
    allow_demask: bool = True,
) -> ConsumerContext:
    policy = ConsumerPolicy(
        policy_id=f"policy-{system_id}",
        system_id=system_id,
        enabled=True,
        pii_types=(PiiType.PERSON, PiiType.EMAIL, PiiType.PHONE),
        allow_demask=allow_demask,
        mask_strategy=strategy_name,
    )
    return ConsumerContext(consumer_id=system_id, policy=policy)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy_name", "strategy", "unknown"),
    (
        ("placeholder", PlaceholderMaskStrategy(), "[[PII:UNKNOWN:9]]"),
        ("competition", CompetitionMaskStrategy(), "<UNKNOWN_9>"),
    ),
)
async def test_llm_reply_restores_reordered_repeats_and_keeps_new_text(
    strategy_name: str,
    strategy: MaskStrategy,
    unknown: str,
) -> None:
    store = MemoryStateStore()
    service = _service(store, strategy)
    context = _context("alfa_tester", strategy_name)

    masked = await service.process(context, "payload-1", _ORIGINAL)
    retry = await service.process(context, "payload-1", _ORIGINAL)
    exact = await service.process(context, "payload-1", masked.result)
    record = store.records[make_session_key("alfa_tester", "payload-1")]
    tokens = {
        record.original_text[entity.original_start : entity.original_end]: entity.rendered_mask
        for entity in record.entities
    }
    reply = (
        f"Ответ:  {tokens[_EMAIL_B]}, повтор {tokens[_EMAIL_B]}; "
        f"человек {tokens[_PERSON]}. Хвост {unknown}!"
    )

    restored = await service.process(context, "payload-1", reply)

    assert masked.outcome is ProcessOutcome.MASKED
    assert retry.result == masked.result
    assert exact.outcome is ProcessOutcome.EXACT_UNMASKED
    assert exact.result == _ORIGINAL
    assert restored.outcome is ProcessOutcome.PRODUCT_DEMASKED
    assert restored.result == (
        f"Ответ:  {_EMAIL_B}, повтор {_EMAIL_B}; человек {_PERSON}. Хвост {unknown}!"
    )
    assert _EMAIL_A not in restored.result
    assert restored.result != _ORIGINAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy_name", "strategy"),
    (
        ("placeholder", PlaceholderMaskStrategy()),
        ("competition", CompetitionMaskStrategy()),
    ),
)
async def test_repeated_same_value_restores_in_new_text(
    strategy_name: str,
    strategy: MaskStrategy,
) -> None:
    service = _service(MemoryStateStore(), strategy)
    context = _context("alfa_tester", strategy_name)
    masked = await service.process(context, "payload-repeat", _REPEAT)
    token = masked.result.split(" / ")[0]
    reply = f"({token}) ({token})"

    restored = await service.process(context, "payload-repeat", reply)

    assert restored.result == f"({_PERSON}) ({_PERSON})"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy_name", "ambiguous", "phone_token"),
    (
        ("placeholder", "[[PII:AMBIGUOUS:1]]", "[[PII:PHONE:2]]"),
        ("competition", "<AMBIGUOUS_1>", "<PHONE_2>"),
    ),
)
async def test_ambiguous_token_stays_while_unique_token_restores(
    strategy_name: str,
    ambiguous: str,
    phone_token: str,
) -> None:
    original = f"{_PERSON} {_EMAIL_A} {_PHONE}"
    store = MemoryStateStore()
    service = _service(store, PlaceholderMaskStrategy())
    context = _context("alfa_tester", strategy_name)
    key = make_session_key("alfa_tester", "payload-ambiguous")
    store.records[key] = SessionRecord(
        original_text=original,
        masked_text="stored-mask",
        entities=(
            MaskedEntity(
                type=PiiType.PERSON,
                original_start=0,
                original_end=len(_PERSON),
                rendered_mask=ambiguous,
                stable_entity_id="person-1",
            ),
            MaskedEntity(
                type=PiiType.EMAIL,
                original_start=len(_PERSON) + 1,
                original_end=len(_PERSON) + 1 + len(_EMAIL_A),
                rendered_mask=ambiguous,
                stable_entity_id="email-1",
            ),
            MaskedEntity(
                type=PiiType.PHONE,
                original_start=len(original) - len(_PHONE),
                original_end=len(original),
                rendered_mask=phone_token,
                stable_entity_id="phone-1",
            ),
        ),
        policy_id="policy-alfa_tester",
        mask_strategy=strategy_name,
    )
    reply = f"  {ambiguous} | {phone_token}. "

    restored = await service.process(context, "payload-ambiguous", reply)

    assert restored.outcome is ProcessOutcome.PRODUCT_DEMASKED
    assert restored.result == f"  {ambiguous} | {_PHONE}. "
    assert _PERSON not in restored.result
    assert _EMAIL_A not in restored.result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy_name", "strategy"),
    (
        ("placeholder", PlaceholderMaskStrategy()),
        ("competition", CompetitionMaskStrategy()),
    ),
)
async def test_other_consumer_and_payload_do_not_receive_mapping(
    strategy_name: str,
    strategy: MaskStrategy,
) -> None:
    service = _service(MemoryStateStore(), strategy)
    owner = _context("owner", strategy_name)
    other = _context("other", strategy_name)
    masked = await service.process(owner, "payload-1", _ORIGINAL)

    foreign_consumer = await service.process(other, "payload-1", masked.result)
    foreign_payload = await service.process(owner, "payload-2", masked.result)

    assert _PERSON not in foreign_consumer.result
    assert _EMAIL_A not in foreign_consumer.result
    assert _PERSON not in foreign_payload.result
    assert _EMAIL_B not in foreign_payload.result
    assert masked.result in foreign_consumer.result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy_name", "strategy"),
    (
        ("placeholder", PlaceholderMaskStrategy()),
        ("competition", CompetitionMaskStrategy()),
    ),
)
async def test_disabled_demask_rejects_modified_reply(
    strategy_name: str,
    strategy: MaskStrategy,
) -> None:
    service = _service(MemoryStateStore(), strategy)
    context = _context("alfa_tester", strategy_name, allow_demask=False)
    masked = await service.process(context, "payload-1", _ORIGINAL)

    with pytest.raises(DemaskNotAllowedError):
        await service.process(context, "payload-1", f"new {masked.result}")
