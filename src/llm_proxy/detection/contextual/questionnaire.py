"""Questionnaire-style labeled field detector."""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from datetime import date

from llm_proxy.detection.contextual.common import CYR, confirmed
from llm_proxy.detection.contextual.labeled import (
    ADDRESS_COMPONENT_LABELS,
    LABEL_VARIANTS,
    iter_address_component_spans,
    looks_like_labeled_form,
    next_label_matches,
    strip_annotation,
    value_terminator,
)
from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import digits_only

_DIGITS = re.compile(r"(?<!\d)(\d{10}|\d{12})(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d{4}(?:[ -]\d{4}){3}|\d{16})(?!\d)")
_NUMERIC_DATE = re.compile(
    r"(?<!\d)(?:(\d{1,2})[./-](\d{1,2})[./-](\d{4})|"
    r"(\d{4})[./-](\d{2})[./-](\d{2}))(?!\d)"
)
_TEXTUAL_DATE = re.compile(
    r"(?<!\d)(\d{1,2})\s+"
    r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
    r"\s+(\d{4})(?:\s*(?:года|\u0433\.?))?",
    re.IGNORECASE,
)
_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
_ORDINALS = {
    "первого": 1,
    "второго": 2,
    "третьего": 3,
    "четвёртого": 4,
    "четвертого": 4,
    "пятого": 5,
    "шестого": 6,
    "седьмого": 7,
    "восьмого": 8,
    "девятого": 9,
    "десятого": 10,
    "одиннадцатого": 11,
    "двенадцатого": 12,
    "тринадцатого": 13,
    "четырнадцатого": 14,
    "пятнадцатого": 15,
    "шестнадцатого": 16,
    "семнадцатого": 17,
    "восемнадцатого": 18,
    "девятнадцатого": 19,
    "двадцатого": 20,
    "тридцатого": 30,
}
_ONES = {
    "один": 1,
    "одна": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
}
_TEENS = {
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
}
_TENS = {
    "двадцать": 20,
    "тридцать": 30,
    "сорок": 40,
    "пятьдесят": 50,
    "шестьдесят": 60,
    "семьдесят": 70,
    "восемьдесят": 80,
    "девяносто": 90,
}
_HUNDREDS = {
    "сто": 100,
    "двести": 200,
    "триста": 300,
    "четыреста": 400,
    "пятьсот": 500,
    "шестьсот": 600,
    "семьсот": 700,
    "восемьсот": 800,
    "девятьсот": 900,
}
_MONTH_ALT = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
_ORD_ALT = "|".join(sorted(_ORDINALS, key=len, reverse=True))
_VERBAL_DATE = re.compile(
    rf"(?:(?P<tens>двадцать|тридцать)\s+)?(?P<day>{_ORD_ALT})\s+"
    rf"(?P<month>{_MONTH_ALT})\s+"
    r"(?P<year>(?:тысяча|тысячи|две\s+тысячи|два\s+тысячи)"
    rf"(?:\s+(?!года\b|\u0433\b)[{CYR}]+){{0,5}})"
    r"(?:\s*(?:года|\u0433\.?))?",
    re.IGNORECASE,
)

_COMPONENT_TYPES = frozenset(pii_type for _label, pii_type in ADDRESS_COMPONENT_LABELS)

_LABEL_TO_TYPE: dict[str, PiiType] = {}
for pii_type, labels in LABEL_VARIANTS.items():
    for label in labels:
        _LABEL_TO_TYPE[label.casefold()] = pii_type


class QuestionnaireDetector:
    """Detect PII values bounded by explicit questionnaire labels."""

    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        enabled = frozenset(enabled_types)
        if not enabled or not looks_like_labeled_form(text):
            return ()

        found: list[Detection] = []
        for match in next_label_matches(text):
            label = match.group(0).rstrip().rstrip(":").strip().casefold()
            # Normalize whitespace inside matched label text.
            label_key = re.sub(r"\s+", " ", label)
            pii_type = _LABEL_TO_TYPE.get(label_key)
            if pii_type is None or pii_type not in enabled:
                continue
            value_start = match.end()
            while value_start < len(text) and text[value_start] in " \t":
                value_start += 1
            value_end, terminated = value_terminator(text, value_start)
            if pii_type == PiiType.PERSON and not terminated:
                continue
            if pii_type == PiiType.PASSPORT_ISSUER and label_key.startswith("паспорт выдан"):
                preview = text[value_start : value_start + 12]
                if re.match(r"\d{1,2}[./-]", preview) or re.match(r"\d{4}-\d{2}-\d{2}", preview):
                    continue
            start, end = strip_annotation(text, value_start, value_end)
            if end <= start:
                continue
            detection = _detection_for(pii_type, text, start, end)
            if detection is not None:
                found.append(detection)

        if enabled & _COMPONENT_TYPES and ":" in text and "адрес" in text.casefold():
            for pii_type, start, end in iter_address_component_spans(text):
                if pii_type in enabled:
                    found.append(confirmed(pii_type, start, end, "questionnaire"))

        return tuple(found)


def _detection_for(pii_type: PiiType, text: str, start: int, end: int) -> Detection | None:
    if pii_type in {PiiType.PERSON, PiiType.CARDHOLDER}:
        return confirmed(pii_type, start, end, "questionnaire", confidence=0.92)
    if pii_type in {PiiType.CITIZENSHIP, PiiType.BIRTH_PLACE}:
        return confirmed(pii_type, start, end, "questionnaire", confidence=0.9)
    if pii_type == PiiType.PASSPORT_ISSUER:
        if end - start < 3:
            return None
        return confirmed(pii_type, start, end, "questionnaire", confidence=0.9)
    if pii_type in {PiiType.BIRTH_DATE, PiiType.PASSPORT_ISSUE_DATE}:
        span = _date_span_inside(text, start, end)
        if span is None:
            return None
        return confirmed(pii_type, span[0], span[1], "questionnaire")
    if pii_type == PiiType.INN:
        match = _DIGITS.search(text, start, end)
        if match is None:
            return None
        return confirmed(PiiType.INN, match.start(), match.end(), "questionnaire", confidence=0.7)
    if pii_type == PiiType.PAYMENT_CARD:
        match = _CARD.search(text, start, end)
        if match is None or len(digits_only(match.group(0))) != 16:
            return None
        return confirmed(
            PiiType.PAYMENT_CARD,
            match.start(),
            match.end(),
            "questionnaire",
            confidence=0.7,
        )
    return None


def _date_span_inside(text: str, start: int, end: int) -> tuple[int, int] | None:
    region = text[start:end]
    for match in _NUMERIC_DATE.finditer(region):
        parts = _numeric_parts(match)
        if parts is not None and _real_date(*parts):
            return start + match.start(), start + match.end()
    for match in _TEXTUAL_DATE.finditer(region):
        month = _MONTHS[match.group(2).casefold()]
        if _real_date(int(match.group(3)), month, int(match.group(1))):
            return start + match.start(), start + match.end()
    for match in _VERBAL_DATE.finditer(region):
        parsed = _verbal_parts(match)
        if parsed is not None and _real_date(*parsed):
            return start + match.start(), start + match.end()
    return None


def _verbal_parts(match: re.Match[str]) -> tuple[int, int, int] | None:
    day = _ORDINALS[match.group("day").casefold()]
    tens = match.group("tens")
    if tens is not None:
        day = _TENS[tens.casefold()] + day
    month = _MONTHS[match.group("month").casefold()]
    year = _parse_verbal_year(match.group("year"))
    if year is None:
        return None
    return year, month, day


def _numeric_parts(match: re.Match[str]) -> tuple[int, int, int] | None:
    if match.group(1) is not None:
        return int(match.group(3)), int(match.group(2)), int(match.group(1))
    if match.group(4) is not None:
        return int(match.group(4)), int(match.group(5)), int(match.group(6))
    return None


def _real_date(year: int, month: int, day: int) -> bool:
    if not 1900 <= year <= 2100:
        return False
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _parse_verbal_year(phrase: str) -> int | None:
    tokens = [token.casefold() for token in re.findall(rf"[{CYR}]+", phrase)]
    if not tokens:
        return None
    total = 0
    index = 0
    if (
        index + 1 < len(tokens)
        and tokens[index] in {"две", "два"}
        and tokens[index + 1] == "тысячи"
    ):
        total = 2000
        index += 2
    elif tokens[index] in {"тысяча", "тысячи"}:
        total = 1000
        index += 1
    else:
        return None
    if index < len(tokens) and tokens[index] in _HUNDREDS:
        total += _HUNDREDS[tokens[index]]
        index += 1
    if index < len(tokens) and tokens[index] in _TEENS:
        total += _TEENS[tokens[index]]
        index += 1
    elif index < len(tokens) and tokens[index] in _ORDINALS:
        total += _ORDINALS[tokens[index]]
        index += 1
    else:
        if index < len(tokens) and tokens[index] in _TENS:
            total += _TENS[tokens[index]]
            index += 1
        if index < len(tokens) and tokens[index] in _ONES:
            total += _ONES[tokens[index]]
            index += 1
        elif index < len(tokens) and tokens[index] in _ORDINALS:
            total += _ORDINALS[tokens[index]]
            index += 1
    if index != len(tokens) or not 1900 <= total <= 2100:
        return None
    return total
