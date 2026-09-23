"""Evaluate labeled questionnaire coverage on an external sample file.

Usage:
  set LLM_PROXY_LABELED_SAMPLE=C:/path/to/synthetic_pdn_requests_200_utf8.txt
  python scripts/eval_labeled_sample.py

Prints aggregate metrics only — never raw field values.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import MANDATORY_PII_TYPES, Detection, PiiType
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.masking.base import MaskContext
from llm_proxy.masking.competition import CompetitionMaskStrategy

_ANNOTATION = re.compile(r"\s*\([^)]*\)\s*$")

_FIELD_LABELS: tuple[tuple[str, PiiType], ...] = (
    ("имя держателя карты", PiiType.CARDHOLDER),
    ("номер платёжной банковской карты", PiiType.PAYMENT_CARD),
    ("номер платежной банковской карты", PiiType.PAYMENT_CARD),
    ("серия и номер водительского удостоверения", PiiType.DRIVER_LICENSE),
    ("серия и номер паспорта", PiiType.PASSPORT),
    ("орган, выдавший паспорт", PiiType.PASSPORT_ISSUER),
    ("дата выдачи паспорта", PiiType.PASSPORT_ISSUE_DATE),
    ("код подразделения", PiiType.PASSPORT_DIVISION_CODE),
    ("место рождения", PiiType.BIRTH_PLACE),
    ("дата рождения", PiiType.BIRTH_DATE),
    ("номер телефона", PiiType.PHONE),
    ("гражданство", PiiType.CITIZENSHIP),
    ("cvv-код", PiiType.CVV),
    ("pin-код карты", PiiType.PIN),
    ("email", PiiType.EMAIL),
    ("инн", PiiType.INN),
    ("фио", PiiType.PERSON),
)

_ADDRESS_COMPONENTS: tuple[tuple[str, PiiType], ...] = (
    ("страна", PiiType.ADDRESS_COUNTRY),
    ("индекс", PiiType.ADDRESS_POSTAL_CODE),
    ("город", PiiType.ADDRESS_CITY),
    ("улица", PiiType.ADDRESS_STREET),
    ("дом", PiiType.ADDRESS_BUILDING),
    ("квартира", PiiType.ADDRESS_UNIT),
)

_ADDRESS_BLOCK = re.compile(
    r"адрес\s*(?:проживания|регистрации)?\s*[—\-:]?\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ExpectedField:
    pii_type: PiiType
    start: int
    end: int


def build_engine() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def _strip_annotation(text: str, start: int, end: int) -> tuple[int, int]:
    value = text[start:end]
    match = _ANNOTATION.search(value)
    if match is not None:
        end = start + match.start()
    while end > start and text[end - 1] in " .,;:":
        end -= 1
    while start < end and text[start] in " \t":
        start += 1
    return start, end


def expected_fields(text: str) -> list[ExpectedField]:
    found: list[ExpectedField] = []
    lower = text.casefold()

    for label, pii_type in _FIELD_LABELS:
        needle = label.casefold() + ":"
        cursor = 0
        while True:
            index = lower.find(needle, cursor)
            if index < 0:
                break
            value_start = index + len(needle)
            while value_start < len(text) and text[value_start] in " \t":
                value_start += 1
            value_end = text.find(";", value_start)
            if value_end < 0:
                value_end = len(text)
            start, end = _strip_annotation(text, value_start, value_end)
            if end > start:
                found.append(ExpectedField(pii_type, start, end))
            cursor = value_end + 1 if value_end < len(text) else len(text)

    for block in _ADDRESS_BLOCK.finditer(text):
        region_start = block.end()
        region_end = text.find(";", region_start)
        if region_end < 0:
            region_end = len(text)
        region = text[region_start:region_end]
        region_lower = region.casefold()
        for label, pii_type in _ADDRESS_COMPONENTS:
            needle = label.casefold() + ":"
            index = region_lower.find(needle)
            if index < 0:
                continue
            value_start = region_start + index + len(needle)
            while value_start < region_end and text[value_start] in " \t":
                value_start += 1
            next_positions = []
            for other, _ in _ADDRESS_COMPONENTS:
                other_at = region_lower.find(other.casefold() + ":", index + len(needle))
                if other_at >= 0:
                    next_positions.append(region_start + other_at)
            value_end = region_end
            if next_positions:
                value_end = min(value_end, min(next_positions))
            comma = text.find(",", value_start, value_end)
            if comma >= 0:
                value_end = min(value_end, comma)
            start, end = _strip_annotation(text, value_start, value_end)
            if end > start:
                found.append(ExpectedField(pii_type, start, end))

    found.sort(key=lambda item: (item.start, item.end, item.pii_type.value))
    return found


def _covers(detection: Detection, field: ExpectedField) -> bool:
    return (
        detection.type == field.pii_type
        and detection.start <= field.start
        and detection.end >= field.end
    )


def evaluate_line(
    engine: PiiEngine, text: str
) -> tuple[int, int, int, Counter[str], Counter[str], int]:
    expected = expected_fields(text)
    detections = list(engine.detect(text, MANDATORY_PII_TYPES))
    covered = 0
    per_ok: Counter[str] = Counter()
    per_miss: Counter[str] = Counter()
    for field in expected:
        if any(_covers(item, field) for item in detections):
            covered += 1
            per_ok[field.pii_type.value] += 1
        else:
            per_miss[field.pii_type.value] += 1

    false_positives = 0
    for detection in detections:
        if not any(
            detection.start < field.end and field.start < detection.end for field in expected
        ):
            false_positives += 1

    strategy = CompetitionMaskStrategy()
    masked = strategy.mask(
        text,
        detections,
        MaskContext(policy_id="eval", mask_strategy="competition"),
    )
    restored = masked.text
    for entity in sorted(masked.entities, key=lambda item: -len(item.rendered_mask)):
        original = text[entity.original_start : entity.original_end]
        restored = restored.replace(entity.rendered_mask, original)
    round_trip_ok = int(restored == text)
    return covered, len(expected), false_positives, per_ok, per_miss, round_trip_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        default=os.environ.get("LLM_PROXY_LABELED_SAMPLE", ""),
        help="Path to UTF-8 sample file with one questionnaire per line",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional line limit")
    args = parser.parse_args(argv)
    if not args.sample:
        print("sample path required via --sample or LLM_PROXY_LABELED_SAMPLE", file=sys.stderr)
        return 2
    path = Path(args.sample)
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        lines = lines[: args.limit]

    engine = build_engine()
    total_covered = 0
    total_expected = 0
    total_fp = 0
    round_trips = 0
    per_ok: Counter[str] = Counter()
    per_miss: Counter[str] = Counter()

    for line in lines:
        covered, expected, fp, ok, miss, rt = evaluate_line(engine, line)
        total_covered += covered
        total_expected += expected
        total_fp += fp
        round_trips += rt
        per_ok.update(ok)
        per_miss.update(miss)

    rate = 0.0 if total_expected == 0 else 100.0 * total_covered / total_expected
    print(f"lines={len(lines)}")
    print(f"fields_covered={total_covered}/{total_expected} ({rate:.2f}%)")
    print(f"false_positives={total_fp}")
    print(f"exact_round_trip={round_trips}/{len(lines)}")
    print("per_type_ok:")
    for key in sorted(set(per_ok) | set(per_miss)):
        print(f"  {key}: {per_ok[key]}/{per_ok[key] + per_miss[key]}")
    print("per_type_miss:")
    for key, count in sorted(per_miss.items()):
        if count:
            print(f"  {key}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
