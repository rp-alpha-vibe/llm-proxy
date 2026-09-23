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
_PERSON = re.compile(r"фио|клиент|заявител|зовут", re.IGNORECASE)
_CONTACT_PERSON = re.compile(r"контактное\s+лицо", re.IGNORECASE)
_CONTACTS = re.compile(r"контакт(?:ы|ные\s+данные)", re.IGNORECASE)
_CONTACT_DETAIL = re.compile(
    r"(?:\+?\d[\d ()-]{6,}\d|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)
_CARDHOLDER = re.compile(
    r"держател|cardholder|владелец карты|имя на карте",
    re.IGNORECASE,
)


class PersonDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PERSON not in enabled_types:
            return ()
        # Questionnaire `ФИО:` fields are owned by QuestionnaireDetector; keep free-form paths.
        if ":" in text and ";" in text:
            lowered = text.casefold()
            form_only = (
                "фио:" in lowered and "зовут" not in lowered and ("контактное лицо" not in lowered)
            )
            if form_only:
                return ()
        field_aware = ";" in text
        found: list[Detection] = []
        for match in _NAME.finditer(text):
            if not _owned_by_person(text, match.start(), match.end(), field_aware=field_aware):
                continue
            found.append(
                confirmed(
                    PiiType.PERSON,
                    match.start(),
                    match.end(),
                    "person",
                    confidence=0.85,
                )
            )
        return tuple(found)


class CardholderDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.CARDHOLDER not in enabled_types:
            return ()
        if ":" in text:
            lowered = text.casefold()
            if (
                "имя держателя карты:" in lowered
                or "держатель карты:" in lowered
                or "cardholder:" in lowered
                or "имя на карте:" in lowered
            ):
                return ()
        field_aware = ";" in text
        found: list[Detection] = []
        for match in _NAME.finditer(text):
            if not _owned_by_cardholder(text, match.start(), match.end(), field_aware=field_aware):
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


def _owned_by_person(text: str, start: int, end: int, *, field_aware: bool) -> bool:
    slice_text, local_start, local_end = _field_slice(text, start, end, field_aware=field_aware)
    person = label_distance(slice_text, local_start, local_end, _PERSON)
    contact_person = label_distance(slice_text, local_start, local_end, _CONTACT_PERSON)
    if person is None or (contact_person is not None and contact_person < person):
        person = contact_person
    if person is None:
        contacts = label_distance(slice_text, local_start, local_end, _CONTACTS)
        detail_start = max(0, local_start - 48)
        detail_end = min(len(slice_text), local_end + 80)
        if contacts is None or _CONTACT_DETAIL.search(slice_text, detail_start, detail_end) is None:
            return False
        person = contacts
    cardholder = label_distance(slice_text, local_start, local_end, _CARDHOLDER)
    return cardholder is None or person <= cardholder


def _owned_by_cardholder(text: str, start: int, end: int, *, field_aware: bool) -> bool:
    slice_text, local_start, local_end = _field_slice(text, start, end, field_aware=field_aware)
    cardholder = label_distance(slice_text, local_start, local_end, _CARDHOLDER)
    if cardholder is None:
        return False
    person = label_distance(slice_text, local_start, local_end, _PERSON)
    return person is None or cardholder < person
