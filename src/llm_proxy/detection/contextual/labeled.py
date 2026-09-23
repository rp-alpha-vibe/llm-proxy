"""Bounded extraction of values after known questionnaire labels."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from llm_proxy.detection.contextual.common import CYR, trim_span
from llm_proxy.detection.models import PiiType

_ANNOTATION = re.compile(r"\s*\([^)]*\)\s*$")
_ORG_PREFIX = re.compile(r"отделен|филиал|офис|банк", re.IGNORECASE)
_INLINE_FIELD_BREAK = re.compile(
    r",\s*(?=(?:"
    r"дата\s+рождения|место\s+рождения|гражданство|"
    r"серия\s+и\s+номер\s+паспорта|орган,\s*выдавший\s+паспорт|"
    r"код\s+подразделения|дата\s+выдачи\s+паспорта|"
    r"серия\s+и\s+номер\s+водительского|"
    r"адрес|email|e-mail|номер\s+телефона|телефон|инн|"
    r"номер\s+плат[её]жной|cvv|pin|пин|имя\s+держателя|"
    r"держатель\s+карты|паспорт|водител"
    r")\b)",
    re.IGNORECASE,
)

LABEL_VARIANTS: dict[PiiType, tuple[str, ...]] = {
    PiiType.PERSON: ("фио",),
    PiiType.BIRTH_DATE: ("дата рождения",),
    PiiType.BIRTH_PLACE: ("место рождения",),
    PiiType.CITIZENSHIP: ("гражданство",),
    PiiType.PASSPORT_ISSUER: (
        "орган, выдавший паспорт",
        "кем выдан документ",
        "паспорт выдан",
    ),
    PiiType.PASSPORT_ISSUE_DATE: ("дата выдачи паспорта",),
    PiiType.INN: ("инн",),
    PiiType.PAYMENT_CARD: (
        "номер платёжной банковской карты",
        "номер платежной банковской карты",
    ),
    PiiType.CARDHOLDER: (
        "имя держателя карты",
        "держатель карты",
        "cardholder",
        "имя на карте",
    ),
}

ADDRESS_COMPONENT_LABELS: tuple[tuple[str, PiiType], ...] = (
    ("страна", PiiType.ADDRESS_COUNTRY),
    ("индекс", PiiType.ADDRESS_POSTAL_CODE),
    ("город", PiiType.ADDRESS_CITY),
    ("улица", PiiType.ADDRESS_STREET),
    ("дом", PiiType.ADDRESS_BUILDING),
    ("квартира", PiiType.ADDRESS_UNIT),
)

_ADDRESS_BLOCK = re.compile(
    rf"(?<![0-9A-Za-z{CYR}])адрес\s*(?:проживания|регистрации|клиента)?"
    r"\s*[—\-:]\s*",
    re.IGNORECASE,
)


def strip_annotation(text: str, start: int, end: int) -> tuple[int, int]:
    start, end = trim_span(text, start, end)
    match = _ANNOTATION.search(text, start, end)
    if match is not None and match.end() == end:
        end = match.start()
        start, end = trim_span(text, start, end)
    return start, end


def compile_label(label: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![0-9A-Za-z{CYR}]){re.escape(label)}\s*:", re.IGNORECASE)


_LABEL_PATTERNS: dict[PiiType, tuple[re.Pattern[str], ...]] = {
    pii_type: tuple(compile_label(label) for label in labels)
    for pii_type, labels in LABEL_VARIANTS.items()
}

_ALL_LABELS_SORTED = tuple(
    sorted(
        (label for labels in LABEL_VARIANTS.values() for label in labels),
        key=len,
        reverse=True,
    )
)
_NEXT_LABEL = re.compile(
    rf"(?<![0-9A-Za-z{CYR}])(?:"
    + "|".join(re.escape(label) for label in _ALL_LABELS_SORTED)
    + r")\s*:",
    re.IGNORECASE,
)


def next_label_matches(text: str) -> Iterable[re.Match[str]]:
    return _NEXT_LABEL.finditer(text)


def field_start_boundary(text: str, index: int) -> int:
    boundary = text.rfind(";", 0, index)
    return 0 if boundary < 0 else boundary + 1


def looks_like_labeled_form(text: str) -> bool:
    """Cheap gate: questionnaire rules only apply when label colons exist."""
    return ":" in text


def value_terminator(text: str, start: int) -> tuple[int, bool]:
    """Return (end, terminated) where terminated means `;`, inline break, or label."""
    end = len(text)
    terminated = False
    semicolon = text.find(";", start)
    search_limit = end if semicolon < 0 else semicolon
    if semicolon >= 0:
        end = semicolon
        terminated = True
    inline = _INLINE_FIELD_BREAK.search(text, start, search_limit)
    if inline is not None:
        end = inline.start()
        terminated = True
        search_limit = end
    next_label = _NEXT_LABEL.search(text, start, search_limit)
    if next_label is not None:
        end = next_label.start()
        terminated = True
    return end, terminated


def _terminator(text: str, start: int) -> tuple[int, bool]:
    return value_terminator(text, start)


def iter_labeled_spans(
    text: str,
    pii_type: PiiType,
    *,
    require_terminator: bool = False,
) -> Iterable[tuple[int, int]]:
    if not looks_like_labeled_form(text):
        return
    for pattern in _LABEL_PATTERNS.get(pii_type, ()):
        for match in pattern.finditer(text):
            value_start = match.end()
            while value_start < len(text) and text[value_start] in " \t":
                value_start += 1
            value_end, terminated = _terminator(text, value_start)
            if require_terminator and not terminated:
                continue
            # "паспорт выдан: <issuer>" must not steal "паспорт выдан <date> <issuer>".
            if pii_type == PiiType.PASSPORT_ISSUER and match.group(0).casefold().startswith(
                "паспорт выдан"
            ):
                preview = text[value_start : value_start + 12]
                if re.match(r"\d{1,2}[./-]", preview) or re.match(r"\d{4}-\d{2}-\d{2}", preview):
                    continue
            start, end = strip_annotation(text, value_start, value_end)
            if end > start:
                yield start, end


def iter_address_component_spans(text: str) -> Iterable[tuple[PiiType, int, int]]:
    if not looks_like_labeled_form(text):
        return
    for block in _ADDRESS_BLOCK.finditer(text):
        prefix = text[max(0, block.start() - 48) : block.start()]
        if _ORG_PREFIX.search(prefix):
            continue
        region_start = block.end()
        region_end, _terminated = _terminator(text, region_start)
        region = text[region_start:region_end]
        region_lower = region.casefold()
        if not any(f"{label}:" in region_lower for label, _ in ADDRESS_COMPONENT_LABELS):
            continue
        for label, pii_type in ADDRESS_COMPONENT_LABELS:
            needle = f"{label}:"
            cursor = 0
            while True:
                found_at = region_lower.find(needle, cursor)
                if found_at < 0:
                    break
                value_start = region_start + found_at + len(needle)
                while value_start < region_end and text[value_start] in " \t":
                    value_start += 1
                next_at = region_end
                for other, _ in ADDRESS_COMPONENT_LABELS:
                    other_at = region_lower.find(f"{other}:", found_at + len(needle))
                    if other_at >= 0:
                        next_at = min(next_at, region_start + other_at)
                value_end = next_at
                comma = text.find(",", value_start, value_end)
                if comma >= 0:
                    value_end = comma
                start, end = strip_annotation(text, value_start, value_end)
                if end > start:
                    yield pii_type, start, end
                cursor = found_at + len(needle)


def labeled_patterns_for(pii_type: PiiType) -> Sequence[re.Pattern[str]]:
    return _LABEL_PATTERNS.get(pii_type, ())
