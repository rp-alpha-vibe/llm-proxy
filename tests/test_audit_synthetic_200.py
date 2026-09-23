"""One-off audit of the 200 synthetic requests supplied by the user.

This audit lives on an isolated branch.  Its expectations are derived only
from explicitly labelled fields in the attached synthetic dataset.
"""

import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from llm_proxy.application.process_service import ProcessService
from llm_proxy.detection.models import MANDATORY_PII_TYPES
from llm_proxy.main import _build_detector
from llm_proxy.masking.competition import CompetitionMaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, make_session_key

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_pdn_requests_200_utf8.txt"
BASIC = {
    "ФИО": "person",
    "дата рождения": "birth_date",
    "место рождения": "birth_place",
    "серия и номер паспорта": "passport",
    "гражданство": "citizenship",
    "орган, выдавший паспорт": "passport_issuer",
    "код подразделения": "passport_division_code",
    "дата выдачи паспорта": "passport_issue_date",
    "серия и номер водительского удостоверения": "driver_license",
    "email": "email",
    "номер телефона": "phone",
    "ИНН": "inn",
    "номер платёжной банковской карты": "card",
    "CVV-код": "cvv",
    "PIN-код карты": "pin",
    "имя держателя карты": "cardholder",
}
ADDRESS = ("country", "postal_code", "city", "street", "house", "apartment")
ADDRESS_TYPES = (
    "address_country",
    "address_postal_code",
    "address_city",
    "address_street",
    "address_house",
    "address_apartment",
)


class MemoryStore:
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

    async def get(self, key: str) -> SessionRecord | None:
        return self.records.get(key)

    async def create_if_absent(self, key: str, record: SessionRecord, ttl_seconds: int) -> bool:
        del ttl_seconds
        if key in self.records:
            return False
        self.records[key] = record
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        del ttl_seconds
        return key in self.records

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


def expected_fields(line: str) -> list[tuple[str, str, int, int]]:
    """Parse labels from the user's fixture without guessing unlabelled values."""
    expected = []
    for label, kind in BASIC.items():
        match = re.search(r"(?:^|;\s*|:\s*)" + re.escape(label) + r":\s*([^;]+)", line)
        if not match:
            raise AssertionError(f"Missing labelled field {label}")
        raw = match.group(1)
        start = match.start(1)
        value = raw.strip().rstrip(".")
        if kind == "birth_place":
            city = re.search(r"город\s+([А-ЯЁа-яё-]+)", raw)
            if city is None:
                raise AssertionError("Birth place has no city")
            start = match.start(1) + city.start(1)
            value = city.group(1)
        elif kind == "citizenship":
            value = value.split(" (", 1)[0]
        elif kind == "inn":
            value = value.split(" (", 1)[0]
        elif kind == "card":
            value = value.split(" (", 1)[0]
        expected.append((kind, value, start, start + len(value)))

    address = re.search(r"адрес — страна:\s*([^;]+)", line)
    if address is None:
        raise AssertionError("Missing address")
    clause = address.group(1)
    parts = re.fullmatch(
        r"(.+?), индекс: (\d{6}), город: ([^,]+), улица: ([^,]+), "
        r"дом: ([^,]+), квартира: (\d+)",
        clause,
    )
    if parts is None:
        raise AssertionError("Unknown address layout: " + clause)
    for kind, pii_type, group in zip(ADDRESS, ADDRESS_TYPES, range(1, 7), strict=True):
        value = parts.group(group)
        if kind == "country":
            value = value.split(" (", 1)[0]
        start = address.start(1) + parts.start(group)
        expected.append((pii_type, value, start, start + len(value)))
    return expected


@pytest.mark.asyncio
async def test_user_supplied_200_requests() -> None:
    import json

    lines = [line for line in FIXTURE.read_text("utf-8").splitlines() if line.strip()]
    assert len(lines) == 200
    detector = _build_detector()
    store = MemoryStore()
    service = ProcessService(store, detector, CompetitionMaskStrategy())
    context = ConsumerContext(
        consumer_id="alfa_tester",
        policy=ConsumerPolicy(
            policy_id="policy-alfa_tester",
            system_id="alfa_tester",
            enabled=True,
            pii_types=MANDATORY_PII_TYPES,
            allow_demask=True,
            mask_strategy="competition",
        ),
    )
    stats: dict[str, Counter[str]] = defaultdict(Counter)
    samples: dict[str, list[dict[str, object]]] = defaultdict(list)
    exact_roundtrip = 0
    retries = 0
    modified_demasks = 0
    mask_no_change = 0
    total_expected = 0
    total_detected = 0

    for line in lines:
        number_match = re.search(r"ТЕСТОВЫЙ ЗАПРОС №(\d+)", line)
        assert number_match
        number = int(number_match.group(1))
        fields = expected_fields(line)
        assert len(fields) == 22
        found = detector.detect(line, MANDATORY_PII_TYPES)
        total_detected += len(found)
        total_expected += len(fields)
        masks = await service.process(context, f"audit-{number}", line)
        mask_no_change += masks.result == line

        for kind, value, start, end in fields:
            overlaps = [
                detection for detection in found
                if detection.start < end and start < detection.end
            ]
            same = [item for item in overlaps if item.type.value == kind]
            covered = set()
            for item in same:
                covered.update(range(max(start, item.start), min(end, item.end)))
            if len(covered) == len(value):
                verdict = "full"
            elif covered:
                verdict = "partial"
            elif overlaps:
                verdict = "other_type"
            else:
                verdict = "missing"
            stats[kind][verdict] += 1
            if verdict != "full" and len(samples[kind]) < 5:
                samples[kind].append(
                    {
                        "request": number,
                        "expected": value,
                        "verdict": verdict,
                        "actual": [
                            {"type": item.type.value, "value": line[item.start:item.end]}
                            for item in overlaps
                        ],
                    }
                )

        retry = await service.process(context, f"audit-{number}", line)
        retries += retry.result == masks.result
        restored = await service.process(context, f"audit-{number}", masks.result)
        exact_roundtrip += restored.result == line
        record = store.records[make_session_key("alfa_tester", f"audit-{number}")]
        if record.entities:
            entity = record.entities[0]
            original = line[entity.original_start:entity.original_end]
            modified = f"Новый ответ: {entity.rendered_mask}! Ещё раз {entity.rendered_mask}."
            product = await service.process(context, f"audit-{number}", modified)
            modified_demasks += product.result == f"Новый ответ: {original}! Ещё раз {original}."

    report = {
        "count": len(lines),
        "expected_fields": total_expected,
        "detected_total": total_detected,
        "masked_no_change": mask_no_change,
        "retry_success": retries,
        "exact_roundtrip_success": exact_roundtrip,
        "modified_demask_success": modified_demasks,
        "stats": {key: dict(value) for key, value in sorted(stats.items())},
        "samples": dict(samples),
    }
    print("AUDIT_REPORT_BEGIN")
    print(json.dumps(report, ensure_ascii=False))
    print("AUDIT_REPORT_END")
    not_full = [
        kind for kind, counts in stats.items() if counts["full"] != len(lines)
    ]
    assert not not_full, f"Categories with missing masking: {not_full}"
