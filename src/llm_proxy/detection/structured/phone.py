import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import digits_only, make_detection

_PHONE = re.compile(r"(?<!\d)(?:\+7|8)(?:[ \t()\-]{0,3}\d){10}(?!\d)")


class PhoneDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.PHONE not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _PHONE.finditer(text):
            digits = digits_only(match.group(0))
            if len(digits) != 11 or digits[0] not in "78":
                continue
            found.append(make_detection(PiiType.PHONE, match.start(), match.end(), "phone"))
        return tuple(found)
