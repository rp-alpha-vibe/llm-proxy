import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.contextual.common import (
    CYR,
    CYR_UPPER,
    G_DOT,
    confirmed,
    label_distance,
    trim_span,
)
from llm_proxy.detection.models import Detection, PiiType

_CITIZENSHIP_LABEL = re.compile(
    r"гражданств[\u0430\u043e\u0443\u0435]|гражданин|гражданка",
    re.IGNORECASE,
)
_COUNTRIES = (
    "Российской Федерации",
    "Российская Федерация",
    "Республики Казахстан",
    "Республика Казахстан",
    "Республики Беларусь",
    "Республика Беларусь",
    "Казахстана",
    "Казахстан",
    "Беларуси",
    "Беларусь",
    "России",
    "Россия",
    "РФ",
)
_BIRTH_PLACE = re.compile(
    rf"(?:место рождения|родил(?:ся|ась)\s+в)\s*[:\-]?\s*"
    rf"((?:{G_DOT}\s*)?[{CYR}][{CYR}-]{{1,}}(?:\s+[{CYR}][{CYR}-]{{1,}}){{0,2}})",
    re.IGNORECASE,
)
_PUBLIC_FIGURE = re.compile(r"пушкин|толст|лермонтов|достоевск|гогол|чехов", re.IGNORECASE)
_CLIENT = re.compile(r"клиент|заявител|фио", re.IGNORECASE)
_ISSUER = re.compile(
    rf"(?:кем выдан|паспорт\s+выдан(?:\u0430|\u043e)?)\s*[:\-]?\s*"
    rf"(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}}\s+)?"
    rf"([{CYR_UPPER}][{CYR}0-9 .\u2116-]{{2,80}})",
    re.IGNORECASE,
)


class CitizenshipDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.CITIZENSHIP not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _CITIZENSHIP_LABEL.finditer(text):
            span = _country_after(text, match.end())
            if span is None:
                continue
            found.append(confirmed(PiiType.CITIZENSHIP, span[0], span[1], "citizenship"))
        return tuple(found)


class BirthPlaceDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.BIRTH_PLACE not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _BIRTH_PLACE.finditer(text):
            start, end = trim_span(text, match.start(1), match.end(1))
            if end <= start or _public_biography(text, match.start()):
                continue
            found.append(confirmed(PiiType.BIRTH_PLACE, start, end, "birth-place"))
        return tuple(found)


class PassportIssuerDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PASSPORT_ISSUER not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _ISSUER.finditer(text):
            start, end = trim_span(text, match.start(1), match.end(1))
            if end - start < 3:
                continue
            found.append(confirmed(PiiType.PASSPORT_ISSUER, start, end, "passport-issuer"))
        return tuple(found)


def _country_after(text: str, label_end: int) -> tuple[int, int] | None:
    window_end = min(len(text), label_end + 40)
    window = text[label_end:window_end]
    folded = window.casefold()
    best: tuple[int, int] | None = None
    for country in _COUNTRIES:
        index = folded.find(country.casefold())
        if index == -1:
            continue
        span = (label_end + index, label_end + index + len(country))
        if best is None or span[0] < best[0] or (span[0] == best[0] and span[1] > best[1]):
            best = span
    return best


def _public_biography(text: str, anchor: int) -> bool:
    left = max(0, anchor - 80)
    window = text[left:anchor]
    if label_distance(window, len(window), len(window), _CLIENT, window=80) is not None:
        return False
    return _PUBLIC_FIGURE.search(window) is not None
