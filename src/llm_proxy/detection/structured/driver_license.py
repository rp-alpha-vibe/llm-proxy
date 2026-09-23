import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import keyword_distance, make_detection

_SPACED = re.compile(r"(?<!\d)\d{2}\s?\d{2}\s+\d{6}(?!\d)")
_COMPACT = re.compile(r"(?<!\d)\d{10}(?!\d)")
_DRIVER_KEYWORDS = ("водительск",)
_PASSPORT_KEYWORDS = ("паспорт",)
_INN_KEYWORDS = ("инн",)


class DriverLicenseDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.DRIVER_LICENSE not in enabled_types:
            return ()
        found: list[Detection] = []
        seen: list[tuple[int, int]] = []
        for pattern in (_SPACED, _COMPACT):
            for match in pattern.finditer(text):
                start, end = match.span()
                if any(start < right and left < end for left, right in seen):
                    continue
                driver = keyword_distance(text, start, end, _DRIVER_KEYWORDS)
                passport = keyword_distance(text, start, end, _PASSPORT_KEYWORDS)
                if driver is None or (passport is not None and passport <= driver):
                    continue
                if pattern is _COMPACT:
                    inn = keyword_distance(text, start, end, _INN_KEYWORDS, whole_word=True)
                    if inn is not None and inn < driver:
                        continue
                found.append(make_detection(PiiType.DRIVER_LICENSE, start, end, "driver-license"))
                seen.append((start, end))
        return tuple(found)
