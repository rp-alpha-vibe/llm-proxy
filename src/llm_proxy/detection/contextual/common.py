import re

from llm_proxy.detection.models import Detection, PiiType

CYR_UPPER = r"\u0410-\u042f\u0401"
CYR_LOWER = r"\u0430-\u044f\u0451"
CYR = CYR_UPPER + CYR_LOWER
G_DOT = r"\u0433\."


def confirmed(
    pii_type: PiiType,
    start: int,
    end: int,
    detector_id: str,
    *,
    confidence: float = 0.9,
) -> Detection:
    return Detection(
        type=pii_type,
        start=start,
        end=end,
        confidence=confidence,
        detector_id=detector_id,
        metadata={"context_confirmed": True},
    )


def label_distance(
    text: str,
    start: int,
    end: int,
    pattern: re.Pattern[str],
    *,
    window: int = 48,
) -> int | None:
    left = max(0, start - window)
    right = min(len(text), end + window)
    best: int | None = None
    for match in pattern.finditer(text, left, right):
        if match.end() > start and match.start() < end:
            distance = 0
        elif match.end() <= start:
            distance = start - match.end()
        else:
            distance = match.start() - end
        if best is None or distance < best:
            best = distance
    return best


def trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while end > start and text[end - 1] in " .,;:":
        end -= 1
    while start < end and text[start] in " ":
        start += 1
    return start, end
