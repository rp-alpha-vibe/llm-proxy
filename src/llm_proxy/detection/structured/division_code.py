import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import keyword_distance, make_detection

_DIVISION = re.compile(r"(?<!\d)\d{3}-\d{3}(?!\d)")
_KEYWORDS = ("подраздел",)


class DivisionCodeDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PASSPORT_DIVISION_CODE not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _DIVISION.finditer(text):
            if keyword_distance(text, match.start(), match.end(), _KEYWORDS) is None:
                continue
            found.append(
                make_detection(
                    PiiType.PASSPORT_DIVISION_CODE,
                    match.start(),
                    match.end(),
                    "division-code",
                )
            )
        return tuple(found)
