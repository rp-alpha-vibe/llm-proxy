import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.contextual.common import CYR, confirmed, label_distance
from llm_proxy.detection.models import Detection, PiiType

_CVV_LABEL = re.compile(r"cvv2?|cvc2?|код безопасности", re.IGNORECASE)
_PIN_LABEL = re.compile(
    rf"(?<![0-9A-Za-z{CYR}])(?:pin|пин)(?![A-Za-z{CYR}])",
    re.IGNORECASE,
)
_CARD = re.compile(r"карт|card", re.IGNORECASE)
_CVV_NUMBER = re.compile(r"(?<!\d)\d{3}(?!\d)")
_PIN_NUMBER = re.compile(r"(?<!\d)\d{4,6}(?!\d)")


class CvvDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.CVV not in enabled_types:
            return ()
        return tuple(
            confirmed(PiiType.CVV, start, end, "cvv", confidence=0.95)
            for start, end in _near_label(text, _CVV_LABEL, _CVV_NUMBER)
        )


class PinDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PIN not in enabled_types:
            return ()
        found: list[Detection] = []
        for start, end in _near_label(text, _PIN_LABEL, _PIN_NUMBER):
            if label_distance(text, start, end, _CARD, window=40) is None:
                continue
            found.append(confirmed(PiiType.PIN, start, end, "pin", confidence=0.95))
        return tuple(found)


def _near_label(
    text: str,
    label: re.Pattern[str],
    number: re.Pattern[str],
    *,
    limit: int = 24,
) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for match in label.finditer(text):
        region_start = match.end()
        region_end = min(len(text), region_start + limit)
        number_match = number.search(text, region_start, region_end)
        if number_match is None:
            continue
        found.append(number_match.span())
    return found
