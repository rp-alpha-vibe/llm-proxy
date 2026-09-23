import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import make_detection

_INN = re.compile(r"(?<!\d)(?:\d{12}|\d{10})(?!\d)")
_INN10 = (2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
_INN12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)


class InnDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.INN not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _INN.finditer(text):
            digits = match.group(0)
            if not _checksum_ok(digits):
                continue
            found.append(
                make_detection(PiiType.INN, match.start(), match.end(), "inn", confidence=0.9)
            )
        return tuple(found)


def _checksum_ok(digits: str) -> bool:
    numbers = [int(char) for char in digits]
    if len(numbers) == 10:
        return _control(numbers[:9], _INN10) == numbers[9]
    if len(numbers) == 12:
        return (
            _control(numbers[:10], _INN11) == numbers[10]
            and _control(numbers[:11], _INN12) == numbers[11]
        )
    return False


def _control(numbers: list[int], coefficients: tuple[int, ...]) -> int:
    return (
        sum(number * coefficient for number, coefficient in zip(numbers, coefficients, strict=True))
        % 11
        % 10
    )
