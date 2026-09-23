import time
from collections.abc import Sequence

import pytest

from llm_proxy.application.process_service import ProcessService
from llm_proxy.application.stubs import SimplePlaceholderMaskStrategy
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import PiiType
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore

_INN10 = "5001007329"
_INN12 = "500100732259"
_PAN = "4111111111111111"
_PAN_GROUPED = "4111 1111 1111 1111"
_PAN_DASHED = "4111-1111-1111-1111"
_TYPES = (
    PiiType.EMAIL,
    PiiType.PHONE,
    PiiType.INN,
    PiiType.PAYMENT_CARD,
    PiiType.PASSPORT,
    PiiType.PASSPORT_DIVISION_CODE,
    PiiType.DRIVER_LICENSE,
)


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


def _engine() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    return PiiEngine(registry)


def _found(text: str, enabled: Sequence[PiiType] = _TYPES) -> list[tuple[PiiType, str]]:
    return [(item.type, text[item.start : item.end]) for item in _engine().detect(text, enabled)]


def test_email_formats_case_punctuation_and_negatives() -> None:
    assert _found("Письмо synthetic@example.test.") == [(PiiType.EMAIL, "synthetic@example.test")]
    assert _found("(USER@example.test),") == [(PiiType.EMAIL, "USER@example.test")]
    assert _found("a.b+tag@example.co.uk") == [(PiiType.EMAIL, "a.b+tag@example.co.uk")]
    assert _found("one@example.test и two@example.test") == [
        (PiiType.EMAIL, "one@example.test"),
        (PiiType.EMAIL, "two@example.test"),
    ]
    assert _found("user@localhost") == []
    assert _found(".user@example.test") == []
    assert _found("user..name@example.test") == []
    assert _found("user@-example.test") == []


def test_process_app_wires_structured_detectors() -> None:
    from llm_proxy.main import _build_detector

    text = "тел. +79001234567, synthetic@example.test"
    found = [
        (item.type, text[item.start : item.end])
        for item in _build_detector().detect(text, (PiiType.PHONE, PiiType.EMAIL))
    ]
    assert found == [
        (PiiType.PHONE, "+79001234567"),
        (PiiType.EMAIL, "synthetic@example.test"),
    ]


def test_phone_formats_and_negatives() -> None:
    samples = (
        "+7 (900) 123-45-67",
        "8 999 123 45 67",
        "+79001234567",
        "8(999)123-45-67",
    )
    for sample in samples:
        assert _found(f"тел. {sample}.") == [(PiiType.PHONE, sample)]
    assert _found("+7 900 111-22-33 и 8 900 444-55-66") == [
        (PiiType.PHONE, "+7 900 111-22-33"),
        (PiiType.PHONE, "8 900 444-55-66"),
    ]
    assert _found("+1 202 555 0147") == []
    assert _found("9001234567") == []
    assert _found("заказ 12345") == []


def test_inn_checksum_lengths_and_negatives() -> None:
    assert _found(f"ИНН {_INN10}.") == [(PiiType.INN, _INN10)]
    assert _found(f"инн {_INN12},") == [(PiiType.INN, _INN12)]
    assert _found(f"{_INN10} {_INN12}") == [
        (PiiType.INN, _INN10),
        (PiiType.INN, _INN12),
    ]
    assert _found("1234567890") == []
    assert _found("123456789012") == []


def test_pan_layouts_luhn_and_long_numbers() -> None:
    assert _found(f"карта {_PAN}.") == [(PiiType.PAYMENT_CARD, _PAN)]
    assert _found(_PAN_GROUPED) == [(PiiType.PAYMENT_CARD, _PAN_GROUPED)]
    assert _found(_PAN_DASHED) == [(PiiType.PAYMENT_CARD, _PAN_DASHED)]
    assert _found(f"{_PAN} {_PAN_GROUPED}") == [
        (PiiType.PAYMENT_CARD, _PAN),
        (PiiType.PAYMENT_CARD, _PAN_GROUPED),
    ]
    assert _found("4111111111111112") == []
    assert _found("41111111111111111111") == []
    assert _found("12345678901234567890") == []


def test_passport_layouts_case_and_context() -> None:
    assert _found("Паспорт 45 12 123456.") == [(PiiType.PASSPORT, "45 12 123456")]
    assert _found("ПАСПОРТ 4512123456") == [(PiiType.PASSPORT, "4512123456")]
    assert _found("серия 12 34 номер 123456") == [
        (PiiType.PASSPORT, "12 34"),
        (PiiType.PASSPORT, "123456"),
    ]
    assert _found("Серия: 1234, номер: 567890") == [
        (PiiType.PASSPORT, "1234"),
        (PiiType.PASSPORT, "567890"),
    ]
    assert _found("паспорт 45 12 123456 и паспорт 98 76 111111") == [
        (PiiType.PASSPORT, "45 12 123456"),
        (PiiType.PASSPORT, "98 76 111111"),
    ]
    assert _found("45 12 123456") == []
    assert _found("1234 567890") == []
    assert _found("водительское удостоверение 11 22 334455") == [
        (PiiType.DRIVER_LICENSE, "11 22 334455")
    ]


def test_division_code_requires_context() -> None:
    assert _found("код подразделения 770-001.") == [(PiiType.PASSPORT_DIVISION_CODE, "770-001")]
    assert _found("ПОДРАЗДЕЛЕНИЯ: 123-456,") == [(PiiType.PASSPORT_DIVISION_CODE, "123-456")]
    assert _found(f"770-001{' ' * 60}код подразделения 111-222") == [
        (PiiType.PASSPORT_DIVISION_CODE, "111-222")
    ]
    assert _found("770-001") == []
    assert _found("код 12-3456") == []


def test_driver_license_formats_case_and_passport_priority() -> None:
    assert _found("водительское удостоверение 11 22 334455.") == [
        (PiiType.DRIVER_LICENSE, "11 22 334455")
    ]
    assert _found("ВОДИТЕЛЬСКОЕ 1122334455") == [(PiiType.DRIVER_LICENSE, "1122334455")]
    assert _found("водительское 11 22 334455 и водительское 98 76 111111") == [
        (PiiType.DRIVER_LICENSE, "11 22 334455"),
        (PiiType.DRIVER_LICENSE, "98 76 111111"),
    ]
    assert _found("11 22 334455") == []
    assert _found("паспорт 45 12 123456, водительское 11 22 334455") == [
        (PiiType.PASSPORT, "45 12 123456"),
        (PiiType.DRIVER_LICENSE, "11 22 334455"),
    ]


def test_mixed_sentence_keeps_distinct_types() -> None:
    text = (
        "synthetic@example.test, +7 (900) 123-45-67, "
        f"ИНН {_INN10}, карта {_PAN_GROUPED}, паспорт 45 12 123456, "
        "код подразделения 770-001, водительское удостоверение 11 22 334455."
    )
    found = _found(text)
    assert found == [
        (PiiType.EMAIL, "synthetic@example.test"),
        (PiiType.PHONE, "+7 (900) 123-45-67"),
        (PiiType.INN, _INN10),
        (PiiType.PAYMENT_CARD, _PAN_GROUPED),
        (PiiType.PASSPORT, "45 12 123456"),
        (PiiType.PASSPORT_DIVISION_CODE, "770-001"),
        (PiiType.DRIVER_LICENSE, "11 22 334455"),
    ]


def test_disabled_type_is_not_returned() -> None:
    assert _found("synthetic@example.test +79001234567", (PiiType.EMAIL,)) == [
        (PiiType.EMAIL, "synthetic@example.test")
    ]


def test_plain_prose_has_no_structured_hits() -> None:
    assert _found("Александр Пушкин родился в Москве 6 июня.") == []


@pytest.mark.asyncio
async def test_structured_mask_exact_unmask_preserves_neighbors() -> None:
    text = (
        "Контакт (synthetic@example.test), тел. +7 (900) 123-45-67, "
        f"ИНН {_INN12}, карта {_PAN_DASHED}, паспорт 45 12 123456, "
        "код подразделения 770-001, водительское удостоверение 11 22 334455."
    )
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=_engine(),
        mask_strategy=SimplePlaceholderMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types=_TYPES,
        allow_demask=True,
        mask_strategy="placeholder",
    )
    context = ConsumerContext(consumer_id="alfa_tester", policy=policy)

    masked = await service.process(context, "payload-structured", text)
    restored = await service.process(context, "payload-structured", masked.result)

    assert "synthetic@example.test" not in masked.result
    assert _PAN_DASHED not in masked.result
    assert "Контакт (" in masked.result
    assert "), тел. " in masked.result
    assert restored.result == text


def test_structured_regex_stays_bounded() -> None:
    engine = _engine()
    samples = (
        "synthetic@example.test " * 20 + "+7 900 123-45-67 " * 10,
        "1" * 100_000,
        "a@" * 20_000 + "example.test",
        "серия " * 5_000 + "номер 123456",
    )
    started = time.perf_counter()
    for sample in samples:
        engine.detect(sample, _TYPES)
    assert time.perf_counter() - started < 2.0
