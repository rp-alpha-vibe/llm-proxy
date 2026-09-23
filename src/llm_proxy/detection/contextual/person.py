# Cyrillic role labels; RUF001 suppressed for marker literals.
# ruff: noqa: RUF001

import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.contextual.common import (
    CYR,
    CYR_LOWER,
    CYR_UPPER,
    confirmed,
    label_distance,
)
from llm_proxy.detection.contextual.labeled import field_start_boundary
from llm_proxy.detection.models import Detection, PiiType

_NAME = re.compile(
    rf"(?<![A-Za-z{CYR}])"
    rf"(?:[{CYR_UPPER}][{CYR_LOWER}]{{1,}}(?:-[{CYR_UPPER}][{CYR_LOWER}]{{1,}})?|[{CYR_UPPER}]{{2,}}"
    rf"|[A-Z][a-z]{{1,}}|[A-Z]{{2,}})"
    rf"(?:[ \t]+(?:[{CYR_UPPER}][{CYR_LOWER}]{{1,}}(?:-[{CYR_UPPER}][{CYR_LOWER}]{{1,}})?"
    rf"|[{CYR_UPPER}]{{2,}}|[A-Z][a-z]{{1,}}|[A-Z]{{2,}})){{1,2}}"
    rf"(?![A-Za-z{CYR}])"
)
_SENTENCE_BREAK = re.compile(rf"\.(?=\s+[{CYR_UPPER}A-Z]|\s*$)|;")
# Immediate grammar link: label ends directly before the name span.
_FIO_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])фио\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_CLIENT_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])клиент[аеу]?\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_APPLICANT_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])заявител\w*\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_CALLED_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])зовут\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_RECIPIENT_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])получател(?:ь|я|ю|ем)?(?:\s+заказа)?\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_CONTACT_PERSON_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])контактное\s+лицо\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_CARDHOLDER_IMMEDIATE = re.compile(
    rf"(?<![A-Za-z{CYR}])(?:держател\w*(?:\s+карты)?|cardholder|"
    rf"владелец\s+карты|имя\s+на\s+карте)\s*[:\-—]?\s*\Z",
    re.IGNORECASE,
)
_CONTACTS = re.compile(r"контакт(?:ы|ные\s+данные)", re.IGNORECASE)
_CONTACT_DETAIL = re.compile(
    r"(?:\+?\d[\d ()-]{6,}\d|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)
_LEADING_ROLE = re.compile(
    r"(?:получател(?:ь|я|ю|ем)?(?:\s+заказа)?|фио|клиент|заявител)"
    r"(?:\s*[:\-—])?\s+",
    re.IGNORECASE,
)
_ROLE_BEFORE = re.compile(
    rf"(?<![A-Za-z{CYR}])(?:фио|клиент[аеу]?|заявител\w*|зовут|"
    rf"получател(?:ь|я|ю|ем)?(?:\s+заказа)?|контактное\s+лицо)\s*[:\-—]?",
    re.IGNORECASE,
)
# Text between a role label and a later coordinated name (A и B / A, B).
_COORD_FILL = re.compile(
    rf"^(?:\s*[{CYR_UPPER}][{CYR_LOWER}\-]*(?:\s+[{CYR_UPPER}][{CYR_LOWER}\-]*){{0,2}}"
    rf"|\s*[A-Z][a-z\-]*(?:\s+[A-Z][a-z\-]*){{0,2}}"
    rf"|\s*[{CYR_UPPER}]{{2,}}(?:\s+[{CYR_UPPER}]{{2,}}){{0,2}}"
    rf"|\s*(?:,|и|или))*\s*$",
)
_PREFIX_WINDOW = 48


class PersonDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PERSON not in enabled_types:
            return ()
        lowered = text.casefold()
        if not any(
            token in lowered
            for token in (
                "фио",
                "клиент",
                "заявител",
                "зовут",
                "получател",
                "контакт",
            )
        ):
            return ()
        # Questionnaire `ФИО:` fields are owned by QuestionnaireDetector; keep free-form paths.
        if ":" in text and ";" in text:
            form_only = (
                "фио:" in lowered
                and "зовут" not in lowered
                and "контактное лицо" not in lowered
                and "получател" not in lowered
            )
            if form_only:
                return ()
        field_aware = ";" in text
        found: list[Detection] = []
        covered: list[tuple[int, int]] = []
        for match in _NAME.finditer(text):
            span = _person_name_span(text, match.start(), match.end())
            if span is None:
                continue
            start, end = span
            if any(start < seen_end and seen_start < end for seen_start, seen_end in covered):
                continue
            if not _owned_by_person(text, start, end, field_aware=field_aware):
                continue
            covered.append((start, end))
            found.append(
                confirmed(
                    PiiType.PERSON,
                    start,
                    end,
                    "person",
                    confidence=0.85,
                )
            )
        return tuple(found)


def _person_name_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Drop leading role words (Получатель/ФИО) and rematch the real name."""
    lead = _LEADING_ROLE.match(text, start)
    if lead is not None and lead.end() <= end:
        rematch = _NAME.match(text, lead.end())
        if rematch is None:
            return None
        return rematch.start(), rematch.end()
    return start, end


class CardholderDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.CARDHOLDER not in enabled_types:
            return ()
        lowered = text.casefold()
        if not any(
            token in lowered
            for token in ("держател", "cardholder", "владелец карты", "имя на карте")
        ):
            return ()
        if ":" in text and (
            "имя держателя карты:" in lowered
            or "держатель карты:" in lowered
            or "cardholder:" in lowered
            or "имя на карте:" in lowered
        ):
            return ()
        found: list[Detection] = []
        for match in _NAME.finditer(text):
            if not _owned_by_cardholder(text, match.start(), match.end()):
                continue
            found.append(
                confirmed(
                    PiiType.CARDHOLDER,
                    match.start(),
                    match.end(),
                    "cardholder",
                    confidence=0.95,
                )
            )
        return tuple(found)


def _field_slice(text: str, start: int, end: int, *, field_aware: bool) -> tuple[str, int, int]:
    """Restrict ownership checks to the current `;`-separated field when present."""
    if not field_aware:
        return text, start, end
    field_start = field_start_boundary(text, start)
    field_end = text.find(";", end)
    if field_end < 0:
        field_end = len(text)
    return text[field_start:field_end], start - field_start, end - field_start


def _prefix_before(text: str, name_start: int) -> str:
    return text[max(0, name_start - _PREFIX_WINDOW) : name_start]


def _immediate(text: str, name_start: int, pattern: re.Pattern[str]) -> bool:
    return pattern.search(_prefix_before(text, name_start)) is not None


def _sentence_bounds(text: str, index: int) -> tuple[int, int]:
    """Inclusive-exclusive bounds of the sentence containing index."""
    start = 0
    for match in _SENTENCE_BREAK.finditer(text, 0, index):
        start = match.end()
    end = len(text)
    following = _SENTENCE_BREAK.search(text, index)
    if following is not None:
        end = following.start()
    while start < end and text[start] in " \t":
        start += 1
    return start, end


def _person_role_confirms(text: str, name_start: int) -> bool:
    if (
        _immediate(text, name_start, _FIO_IMMEDIATE)
        or _immediate(text, name_start, _CLIENT_IMMEDIATE)
        or _immediate(text, name_start, _APPLICANT_IMMEDIATE)
        or _immediate(text, name_start, _CALLED_IMMEDIATE)
        or _immediate(text, name_start, _RECIPIENT_IMMEDIATE)
        or _immediate(text, name_start, _CONTACT_PERSON_IMMEDIATE)
    ):
        return True
    return _coordinated_after_role(text, name_start)


def _coordinated_after_role(text: str, name_start: int) -> bool:
    """Allow «ФИО: A и B» / «зовут A и B» within the same sentence."""
    sent_start, _sent_end = _sentence_bounds(text, name_start)
    # Bound the scan: roles sit near the name list, not across a huge prefix.
    scan_from = max(sent_start, name_start - 120)
    region = text[scan_from:name_start]
    if _ROLE_BEFORE.search(region) is None:
        return False
    full = text[sent_start:name_start]
    roles = list(_ROLE_BEFORE.finditer(full))
    if not roles:
        return False
    between = full[roles[-1].end() :]
    return between != "" and _COORD_FILL.fullmatch(between) is not None


def _owned_by_person(text: str, start: int, end: int, *, field_aware: bool) -> bool:
    if _immediate(text, start, _CARDHOLDER_IMMEDIATE):
        return False
    if _person_role_confirms(text, start):
        return True
    # «контакты …: Name, +phone» — same sentence only, not cross-sentence distance.
    slice_text, local_start, _local_end = _field_slice(text, start, end, field_aware=field_aware)
    sent_start, sent_end = _sentence_bounds(slice_text, local_start)
    sentence = slice_text[sent_start:sent_end]
    local_in_sent = local_start - sent_start
    contacts = label_distance(sentence, local_in_sent, local_in_sent + (end - start), _CONTACTS)
    if contacts is None:
        return False
    detail_start = max(0, local_in_sent - 48)
    detail_end = min(len(sentence), local_in_sent + (end - start) + 80)
    return _CONTACT_DETAIL.search(sentence, detail_start, detail_end) is not None


def _owned_by_cardholder(text: str, start: int, end: int) -> bool:
    del end
    return _immediate(text, start, _CARDHOLDER_IMMEDIATE)
