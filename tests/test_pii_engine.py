from collections.abc import Collection, Sequence

import pytest

from llm_proxy.application.process_service import ProcessService
from llm_proxy.application.stubs import SimpleEmailDetector, SimplePlaceholderMaskStrategy
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import Detection, Detector, PiiType
from llm_proxy.detection.registry import DetectorPriority, DetectorRegistry
from llm_proxy.detection.text_view import TextView
from llm_proxy.masking.base import MaskContext, apply_replacements
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore


class MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

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
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        return key in self.records

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


class SpanDetector(Detector):
    def __init__(
        self,
        spans: Sequence[tuple[PiiType, int, int, float]],
        *,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        detector_id: str = "span",
    ) -> None:
        self._spans = spans
        self._metadata = {} if metadata is None else metadata
        self._detector_id = detector_id
        self.calls = 0

    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        del text
        self.calls += 1
        return tuple(
            Detection(
                type=pii_type,
                start=start,
                end=end,
                confidence=confidence,
                detector_id=self._detector_id,
                metadata=self._metadata,
            )
            for pii_type, start, end, confidence in self._spans
            if pii_type in enabled_types
        )


class FindDetector(Detector):
    def __init__(
        self,
        needle: str,
        pii_type: PiiType,
        *,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        self._needle = needle
        self._pii_type = pii_type
        self._metadata = {} if metadata is None else metadata

    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if self._pii_type not in enabled_types:
            return ()
        start = text.find(self._needle)
        if start < 0:
            return ()
        return (
            Detection(
                type=self._pii_type,
                start=start,
                end=start + len(self._needle),
                confidence=0.8,
                detector_id="find",
                metadata=self._metadata,
            ),
        )


def test_text_view_keeps_cyrillic_case_and_punctuation() -> None:
    text = "«Иван», USER"
    view = TextView.from_text(text)

    assert view.normalized == text
    assert view.to_original_span(1, 5) == (1, 5)


def test_text_view_maps_length_changing_invisible_characters() -> None:
    original = "a\u200bb@example.test"
    view = TextView.from_text(original)

    assert view.normalized == "ab@example.test"
    assert view.to_original_span(0, len(view.normalized)) == (0, len(original))


def test_registry_skips_detectors_outside_enabled_types() -> None:
    phone = SpanDetector(((PiiType.PHONE, 0, 1, 1.0),))
    email = SpanDetector(((PiiType.EMAIL, 0, 1, 1.0),))
    registry = DetectorRegistry()
    registry.register(phone, types=(PiiType.PHONE,), priority=DetectorPriority.STRUCTURED)
    registry.register(email, types=(PiiType.EMAIL,), priority=DetectorPriority.STRUCTURED)

    selected = registry.for_types((PiiType.EMAIL,))

    assert len(selected) == 1
    assert selected[0].detector is email
    assert phone.calls == 0


def test_context_requires_confirmation_and_matches_cyrillic_anchor_case() -> None:
    distant = _engine(
        (
            SpanDetector(((PiiType.PERSON, 1, 5, 0.4),), metadata={"context_anchor": "РОДИЛСЯ"}),
            DetectorPriority.GENERIC,
            (PiiType.PERSON,),
        ),
    )
    near = _engine(
        (
            FindDetector("Иван", PiiType.PERSON, metadata={"context_anchor": "РОДИЛСЯ"}),
            DetectorPriority.GENERIC,
            (PiiType.PERSON,),
        ),
    )

    assert distant.detect("«Иван»" + (" " * 50) + "родился", (PiiType.PERSON,)) == ()
    confirmed = near.detect("родился «Иван»", (PiiType.PERSON,))

    assert len(confirmed) == 1
    assert confirmed[0].start == 9
    assert confirmed[0].end == 13


def test_structured_span_beats_overlapping_generic_and_keeps_adjacent() -> None:
    engine = _engine(
        (
            SpanDetector(((PiiType.EMAIL, 0, 4, 1.0),), detector_id="structured"),
            DetectorPriority.STRUCTURED,
            (PiiType.EMAIL,),
        ),
        (
            SpanDetector(
                ((PiiType.PERSON, 2, 6, 0.9),),
                metadata={"context_confirmed": True},
                detector_id="generic",
            ),
            DetectorPriority.GENERIC,
            (PiiType.PERSON,),
        ),
        (
            SpanDetector(
                ((PiiType.PHONE, 4, 8, 1.0),),
                metadata={"context_confirmed": True},
                detector_id="adjacent",
            ),
            DetectorPriority.CONTEXT,
            (PiiType.PHONE,),
        ),
    )

    detections = engine.detect("xxxxYYYY", (PiiType.EMAIL, PiiType.PERSON, PiiType.PHONE))

    assert [(item.type, item.start, item.end) for item in detections] == [
        (PiiType.EMAIL, 0, 4),
        (PiiType.PHONE, 4, 8),
    ]


def test_engine_projects_email_through_invisible_characters_and_punctuation() -> None:
    registry = DetectorRegistry()
    registry.register(
        SimpleEmailDetector(),
        types=(PiiType.EMAIL,),
        priority=DetectorPriority.STRUCTURED,
    )
    engine = PiiEngine(registry)
    text = "(a\u200bb@example.test),"

    detections = engine.detect(text, (PiiType.EMAIL,))

    assert len(detections) == 1
    assert text[detections[0].start : detections[0].end] == "a\u200bb@example.test"
    assert detections[0].start > 0
    assert detections[0].end < len(text)


def test_engine_finds_cyrillic_name_without_surrounding_punctuation() -> None:
    engine = _engine(
        (
            FindDetector(
                "Иван",
                PiiType.PERSON,
                metadata={"context_confirmed": True},
            ),
            DetectorPriority.CONTEXT,
            (PiiType.PERSON,),
        ),
    )

    detections = engine.detect("«Иван».", (PiiType.PERSON,))

    assert len(detections) == 1
    assert detections[0].start == 1
    assert detections[0].end == 5


def test_replacements_apply_from_right_to_left() -> None:
    masked = apply_replacements("aaaa", ((0, 2, "XXX"), (2, 4, "YYYY")))

    assert masked == "XXXYYYY"

    result = SimplePlaceholderMaskStrategy().mask(
        "aaaa",
        (
            Detection(
                type=PiiType.PERSON,
                start=0,
                end=2,
                confidence=1.0,
                detector_id="left",
            ),
            Detection(
                type=PiiType.EMAIL,
                start=2,
                end=4,
                confidence=1.0,
                detector_id="right",
            ),
        ),
        MaskContext(policy_id="policy-test", mask_strategy="placeholder"),
    )

    assert result.text.startswith("[[PII:PERSON:1]]")
    assert result.text.endswith("[[PII:EMAIL:2]]")
    assert result.entities[0].original_start == 0
    assert result.entities[1].original_end == 4


@pytest.mark.asyncio
async def test_new_detector_is_added_without_changing_process_service() -> None:
    registry = DetectorRegistry()
    registry.register(
        SimpleEmailDetector(),
        types=(PiiType.EMAIL,),
        priority=DetectorPriority.STRUCTURED,
    )
    registry.register(
        FindDetector("Иван", PiiType.PERSON, metadata={"context_confirmed": True}),
        types=(PiiType.PERSON,),
        priority=DetectorPriority.CONTEXT,
    )
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=PiiEngine(registry),
        mask_strategy=SimplePlaceholderMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types=(PiiType.PERSON, PiiType.EMAIL),
        allow_demask=True,
        mask_strategy="placeholder",
    )

    result = await service.process(
        ConsumerContext(consumer_id="alfa_tester", policy=policy),
        "payload-1",
        "«Иван» USER@example.test",
    )

    assert "[[PII:PERSON:1]]" in result.result
    assert "[[PII:EMAIL:2]]" in result.result
    assert "Иван" not in result.result
    assert "USER@example.test" not in result.result


def _engine(
    *registrations: tuple[Detector, DetectorPriority, tuple[PiiType, ...]],
) -> PiiEngine:
    registry = DetectorRegistry()
    for detector, priority, types in registrations:
        registry.register(detector, types=types, priority=priority)
    return PiiEngine(registry)
