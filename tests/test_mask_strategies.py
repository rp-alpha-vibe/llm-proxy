import pytest

from llm_proxy.application.process_service import ProcessOutcome, ProcessService
from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.main import _build_mask_strategy
from llm_proxy.masking.base import MaskContext
from llm_proxy.masking.competition import CompetitionMaskStrategy
from llm_proxy.masking.placeholder import PlaceholderMaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore

_FIRST = "demo@example.com"
_SECOND = "other@example.com"


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


def _detection(text: str, value: str, *, start: int | None = None) -> Detection:
    if start is None:
        start = text.index(value)
    return Detection(
        type=PiiType.EMAIL,
        start=start,
        end=start + len(value),
        confidence=1.0,
        detector_id="fixture",
    )


def _context(strategy: str) -> MaskContext:
    return MaskContext(policy_id="policy-test", mask_strategy=strategy)


def test_same_detections_render_differently_without_touching_neighbors() -> None:
    text = f"({_FIRST})."
    detection = _detection(text, _FIRST)
    placeholder = PlaceholderMaskStrategy().mask(text, (detection,), _context("placeholder"))
    competition = CompetitionMaskStrategy().mask(text, (detection,), _context("competition"))

    assert placeholder.text == "([[PII:EMAIL:1]])."
    assert competition.text == "(<EMAIL_1>)."
    assert placeholder.entities[0].stable_entity_id == "email-1"
    assert competition.entities[0].rendered_mask != placeholder.entities[0].rendered_mask


def test_repeated_value_keeps_one_token_and_unique_span_ids() -> None:
    text = f"{_FIRST} and {_FIRST}"
    second = text.index(_FIRST, len(_FIRST))
    detections = (_detection(text, _FIRST), _detection(text, _FIRST, start=second))
    result = PlaceholderMaskStrategy().mask(text, detections, _context("placeholder"))

    assert result.text == "[[PII:EMAIL:1]] and [[PII:EMAIL:1]]"
    assert result.entities[0].stable_entity_id == "email-1"
    assert result.entities[1].stable_entity_id == "email-1#2"
    assert result.entities[0].rendered_mask == result.entities[1].rendered_mask


def test_different_values_get_different_tokens() -> None:
    text = f"{_FIRST} {_SECOND}"
    detections = (
        _detection(text, _FIRST),
        _detection(text, _SECOND, start=text.index(_SECOND)),
    )
    result = CompetitionMaskStrategy().mask(text, detections, _context("competition"))

    assert result.text == "<EMAIL_1> <EMAIL_2>"


def test_existing_token_does_not_collide_with_a_new_mask() -> None:
    text = f"see [[PII:EMAIL:1]] and {_FIRST}"
    result = PlaceholderMaskStrategy().mask(
        text,
        (_detection(text, _FIRST),),
        _context("placeholder"),
    )

    assert result.text == "see [[PII:EMAIL:1]] and [[PII:EMAIL:2]]"


def test_router_follows_policy_strategy() -> None:
    text = _FIRST
    detection = _detection(text, _FIRST)
    router = _build_mask_strategy()

    competition = router.mask(text, (detection,), _context("competition"))
    placeholder = router.mask(text, (detection,), _context("placeholder"))

    assert competition.text == "<EMAIL_1>"
    assert placeholder.text == "[[PII:EMAIL:1]]"


@pytest.mark.asyncio
async def test_requirements_illustration_restores_reordered_repeated_masks() -> None:
    text = f"{_FIRST} {_SECOND}"
    detections = (
        _detection(text, _FIRST),
        _detection(text, _SECOND, start=text.index(_SECOND)),
    )
    strategy = CompetitionMaskStrategy()
    masked = strategy.mask(text, detections, _context("competition"))
    first = masked.entities[0].rendered_mask
    second = masked.entities[1].rendered_mask
    reply = f"Основной: {second}. Копия: {first}. Повтор: {second}."
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=_UnusedDetector(),
        mask_strategy=strategy,
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types=(PiiType.EMAIL,),
        allow_demask=True,
        mask_strategy="competition",
    )
    context = ConsumerContext(consumer_id="alfa_tester", policy=policy)
    await service.process(context, "payload-1", text)
    restored = await service.process(context, "payload-1", reply)

    assert restored.outcome is ProcessOutcome.PRODUCT_DEMASKED
    assert restored.result == f"Основной: {_SECOND}. Копия: {_FIRST}. Повтор: {_SECOND}."


class _UnusedDetector:
    def detect(self, text: str, enabled_types: object) -> tuple[Detection, ...]:
        return (
            _detection(text, _FIRST),
            _detection(text, _SECOND, start=text.index(_SECOND)),
        )
