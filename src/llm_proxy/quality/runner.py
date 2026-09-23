import asyncio
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from llm_proxy.application.process_service import ProcessService
from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import MANDATORY_PII_TYPES, PiiType
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.masking.base import MaskContext
from llm_proxy.masking.placeholder import PlaceholderMaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.quality.gate import MAX_NEGATIVE_DETECTIONS, MIN_F1, MIN_ROUND_TRIP_RATE
from llm_proxy.quality.schema import QualityFixture
from llm_proxy.state.models import SessionRecord, StateStore

CORPUS_PATH = Path(__file__).with_name("corpus.yaml")


class _MemoryStateStore(StateStore):
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


@dataclass
class TypeScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        total = self.tp + self.fp
        return 1.0 if total == 0 else self.tp / total

    @property
    def recall(self) -> float:
        total = self.tp + self.fn
        return 1.0 if total == 0 else self.tp / total

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 0.0 if total == 0 else 2 * self.precision * self.recall / total


@dataclass
class QualityReport:
    fixture_count: int
    scores: dict[str, TypeScore]
    round_trip_passes: int
    negative_detections: int
    mismatches: tuple[str, ...] = ()
    round_trip_failures: tuple[str, ...] = ()
    uncovered: tuple[str, ...] = ()

    @property
    def round_trip_rate(self) -> float:
        if self.fixture_count == 0:
            return 0.0
        return self.round_trip_passes / self.fixture_count

    @property
    def ok(self) -> bool:
        if self.uncovered or self.mismatches or self.round_trip_failures:
            return False
        if self.negative_detections > MAX_NEGATIVE_DETECTIONS:
            return False
        if self.round_trip_rate < MIN_ROUND_TRIP_RATE:
            return False
        return all(
            score.f1 >= MIN_F1 for score in self.scores.values() if score.tp + score.fp + score.fn
        )


def load_corpus(path: Path = CORPUS_PATH) -> tuple[QualityFixture, ...]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("quality corpus must be a list")
    fixtures = tuple(QualityFixture.model_validate(item) for item in raw)
    ids = [item.id for item in fixtures]
    if len(ids) != len(set(ids)):
        raise ValueError("quality fixture ids must be unique")
    for fixture in fixtures:
        fixture.resolved_spans()
    return fixtures


def build_engine() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def evaluate(engine: PiiEngine | None = None) -> QualityReport:
    return asyncio.run(_evaluate(engine or build_engine()))


async def _evaluate(engine: PiiEngine) -> QualityReport:
    fixtures = load_corpus()
    scores: dict[str, TypeScore] = defaultdict(TypeScore)
    mismatches: list[str] = []
    round_trip_failures: list[str] = []
    round_trip_passes = 0
    negative_detections = 0
    expected_types: set[str] = set()

    for fixture in fixtures:
        expected = fixture.resolved_spans()
        detected = tuple(
            (item.type, item.start, item.end)
            for item in engine.detect(fixture.input, fixture.enabled_types)
        )
        expected_set = set(expected)
        detected_set = set(detected)
        for pii_type, _start, _end in expected:
            expected_types.add(pii_type.value)
        for span in expected_set:
            scores[span[0].value].tp += 1 if span in detected_set else 0
            scores[span[0].value].fn += 0 if span in detected_set else 1
        for span in detected_set:
            if span not in expected_set:
                scores[span[0].value].fp += 1
        if expected_set != detected_set:
            mismatches.append(_mismatch_line(fixture, expected, detected))
        if "negative" in fixture.tags:
            negative_detections += len(detected)
        if fixture.round_trip and await _round_trip(engine, fixture):
            round_trip_passes += 1
        elif fixture.round_trip:
            round_trip_failures.append(fixture.id)

    uncovered = tuple(
        pii_type.value for pii_type in MANDATORY_PII_TYPES if pii_type.value not in expected_types
    )
    return QualityReport(
        fixture_count=len(fixtures),
        scores=dict(scores),
        round_trip_passes=round_trip_passes,
        negative_detections=negative_detections,
        mismatches=tuple(mismatches),
        round_trip_failures=tuple(round_trip_failures),
        uncovered=uncovered,
    )


def render_report(report: QualityReport) -> str:
    lines = [
        f"corpus_fixtures: {report.fixture_count}",
        f"local_min_f1: {MIN_F1}",
        f"local_min_round_trip: {MIN_ROUND_TRIP_RATE}",
        "local_metrics_are_not_official_alfa_scoring: true",
        "type\ttp\tfp\tfn\tprecision\trecall\tf1",
    ]
    for name in sorted(report.scores):
        score = report.scores[name]
        lines.append(
            f"{name}\t{score.tp}\t{score.fp}\t{score.fn}\t"
            f"{score.precision:.3f}\t{score.recall:.3f}\t{score.f1:.3f}"
        )
    lines.append(
        f"round_trip: {report.round_trip_passes}/{report.fixture_count} "
        f"({report.round_trip_rate:.3f})"
    )
    lines.append(f"negative_detections: {report.negative_detections}")
    lines.append(f"uncovered: {', '.join(report.uncovered) if report.uncovered else 'none'}")
    if report.mismatches:
        lines.append("mismatches:")
        lines.extend(f"- {line}" for line in report.mismatches)
    if report.round_trip_failures:
        lines.append("round_trip_failures: " + ", ".join(report.round_trip_failures))
    lines.append(f"gate: {'pass' if report.ok else 'fail'}")
    return "\n".join(lines)


async def _round_trip(engine: PiiEngine, fixture: QualityFixture) -> bool:
    service = ProcessService(
        state_store=_MemoryStateStore(),
        detector=engine,
        mask_strategy=PlaceholderMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-quality",
        system_id="quality",
        enabled=True,
        pii_types=fixture.enabled_types,
        allow_demask=True,
        mask_strategy="placeholder",
    )
    context = ConsumerContext(consumer_id="quality", policy=policy)
    masked = await service.process(context, fixture.id, fixture.input)
    restored = await service.process(context, fixture.id, masked.result)
    if restored.result != fixture.input:
        return False
    expected = fixture.resolved_spans()
    if not expected:
        return masked.result == fixture.input
    # Entity/offset check: short house/unit digits must be covered by a real replacement,
    # not by a substring search that collides with placeholder indices or other numbers.
    detections = tuple(engine.detect(fixture.input, fixture.enabled_types))
    direct = PlaceholderMaskStrategy().mask(
        fixture.input,
        detections,
        MaskContext(policy_id="policy-quality", mask_strategy="placeholder"),
    )
    covered = {
        (entity.type, entity.original_start, entity.original_end) for entity in direct.entities
    }
    expected_set = set(expected)
    if not expected_set <= covered:
        return False
    return all(
        fixture.input[entity.original_start : entity.original_end] != entity.rendered_mask
        for entity in direct.entities
        if (entity.type, entity.original_start, entity.original_end) in expected_set
    )


def _mismatch_line(
    fixture: QualityFixture,
    expected: tuple[tuple[PiiType, int, int], ...],
    detected: tuple[tuple[PiiType, int, int], ...],
) -> str:
    def show(spans: tuple[tuple[PiiType, int, int], ...]) -> str:
        parts = [f"{pii_type.value}:{fixture.input[start:end]!r}" for pii_type, start, end in spans]
        return ", ".join(parts) if parts else "none"

    return f"{fixture.id} expected [{show(expected)}] detected [{show(detected)}]"
