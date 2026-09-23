import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import keyword_distance, make_detection

_SPACED = re.compile(r"(?<!\d)\d{2}\s?\d{2}\s+\d{6}(?!\d)")
_COMPACT = re.compile(r"(?<!\d)\d{10}(?!\d)")
_LABELED = re.compile(
    r"сери[яи]\s*[:№#]?\s*(\d{2}\s?\d{2})\s*[,;]?\s*номер\s*[:№#]?\s*(\d{6})(?!\d)",
    re.IGNORECASE,
)
_PASSPORT_KEYWORDS = ("паспорт",)
_DRIVER_KEYWORDS = ("водительск",)
_INN_KEYWORDS = ("инн",)


class PassportDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PASSPORT not in enabled_types:
            return ()
        found: list[Detection] = []
        covered: list[tuple[int, int]] = []
        for match in _LABELED.finditer(text):
            if not _prefers_passport(text, match.start(), match.end()):
                continue
            for group_index in (1, 2):
                start, end = match.span(group_index)
                found.append(make_detection(PiiType.PASSPORT, start, end, "passport"))
                covered.append((start, end))
        for pattern in (_SPACED, _COMPACT):
            for match in pattern.finditer(text):
                start, end = match.span()
                if any(start < right and left < end for left, right in covered):
                    continue
                if keyword_distance(text, start, end, _PASSPORT_KEYWORDS) is None:
                    continue
                if pattern is _COMPACT and _closer_keyword(
                    text,
                    start,
                    end,
                    _INN_KEYWORDS,
                    _PASSPORT_KEYWORDS,
                ):
                    continue
                if not _prefers_passport(text, start, end):
                    continue
                found.append(make_detection(PiiType.PASSPORT, start, end, "passport"))
                covered.append((start, end))
        return tuple(found)


def _closer_keyword(
    text: str,
    start: int,
    end: int,
    preferred: tuple[str, ...],
    other: tuple[str, ...],
) -> bool:
    preferred_distance = keyword_distance(text, start, end, preferred, whole_word=True)
    if preferred_distance is None:
        return False
    other_distance = keyword_distance(text, start, end, other)
    return other_distance is None or preferred_distance < other_distance


def _prefers_passport(text: str, start: int, end: int) -> bool:
    passport = keyword_distance(text, start, end, _PASSPORT_KEYWORDS)
    driver = keyword_distance(text, start, end, _DRIVER_KEYWORDS)
    if driver is None:
        return True
    if passport is None:
        return False
    return passport <= driver
