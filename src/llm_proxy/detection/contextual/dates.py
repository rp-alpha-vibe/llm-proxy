import re
from collections.abc import Callable, Collection, Sequence
from datetime import date

from llm_proxy.detection.contextual.common import confirmed, label_distance
from llm_proxy.detection.models import Detection, PiiType

_NUMERIC = re.compile(
    r"(?<!\d)(?:(\d{1,2})[./-](\d{1,2})[./-](\d{4})|(\d{4})-(\d{2})-(\d{2}))(?!\d)"
)
_TEXTUAL = re.compile(
    r"(?<!\d)(\d{1,2})\s+"
    r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
    r"\s+(\d{4})",
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
_BIRTH = re.compile(r"рожд(?:ения|ение|ён|ен)|родил(?:ся|ась|ись)", re.IGNORECASE)
_ISSUE = re.compile(r"выдач|выдан", re.IGNORECASE)


class BirthDateDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.BIRTH_DATE not in enabled_types:
            return ()
        return _collect(text, PiiType.BIRTH_DATE, "birth-date", _is_birth)


class PassportIssueDateDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PASSPORT_ISSUE_DATE not in enabled_types:
            return ()
        return _collect(text, PiiType.PASSPORT_ISSUE_DATE, "passport-issue-date", _is_issue)


def _collect(
    text: str,
    pii_type: PiiType,
    detector_id: str,
    predicate: Callable[[str, int, int], bool],
) -> tuple[Detection, ...]:
    found: list[Detection] = []
    for start, end in _date_spans(text):
        if predicate(text, start, end):
            found.append(confirmed(pii_type, start, end, detector_id))
    return tuple(found)


def _is_birth(text: str, start: int, end: int) -> bool:
    birth = label_distance(text, start, end, _BIRTH)
    if birth is None:
        return False
    issue = label_distance(text, start, end, _ISSUE)
    return issue is None or birth <= issue


def _is_issue(text: str, start: int, end: int) -> bool:
    issue = label_distance(text, start, end, _ISSUE)
    if issue is None:
        return False
    birth = label_distance(text, start, end, _BIRTH)
    return birth is None or issue < birth


def _date_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _NUMERIC.finditer(text):
        parsed = _numeric_parts(match)
        if parsed is not None and _real_date(*parsed):
            spans.append(match.span())
    for match in _TEXTUAL.finditer(text):
        month = _MONTHS[match.group(2).casefold()]
        if _real_date(int(match.group(3)), month, int(match.group(1))):
            spans.append((match.start(1), match.end(3)))
    return spans


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
