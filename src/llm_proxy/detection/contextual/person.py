import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.contextual.common import (
    CYR,
    CYR_LOWER,
    CYR_UPPER,
    confirmed,
    label_distance,
)
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
        found: list[Detection] = []
        for match in _NAME.finditer(text):
            if not _owned_by_person(text, match.start(), match.end()):
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


def _owned_by_person(text: str, start: int, end: int) -> bool:
    person = label_distance(text, start, end, _PERSON)
    contact_person = label_distance(text, start, end, _CONTACT_PERSON)
    if person is None or (contact_person is not None and contact_person < person):
        person = contact_person
    if person is None:
        contacts = label_distance(text, start, end, _CONTACTS)
        detail_start = max(0, start - 48)
        detail_end = min(len(text), end + 80)
        if contacts is None or _CONTACT_DETAIL.search(text, detail_start, detail_end) is None:
            return False
        person = contacts
    cardholder = label_distance(text, start, end, _CARDHOLDER)
    return cardholder is None or person <= cardholder


def _owned_by_cardholder(text: str, start: int, end: int) -> bool:
    cardholder = label_distance(text, start, end, _CARDHOLDER)
    if cardholder is None:
        return False
    person = label_distance(text, start, end, _PERSON)
    return person is None or cardholder < person
