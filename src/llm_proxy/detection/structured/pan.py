import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import digits_only, make_detection

_PAN = re.compile(r"(?<!\d)(?:\d{4}(?:[ -]\d{4}){3}|\d{16})(?!\d)")


class PanDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PAYMENT_CARD not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _PAN.finditer(text):
            digits = digits_only(match.group(0))
            if len(digits) != 16 or not _luhn_ok(digits):
                continue
            found.append(make_detection(PiiType.PAYMENT_CARD, match.start(), match.end(), "pan"))
        return tuple(found)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0
