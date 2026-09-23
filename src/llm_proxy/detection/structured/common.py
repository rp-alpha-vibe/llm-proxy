from llm_proxy.detection.models import Detection, PiiType


def digits_only(value: str) -> str:
    return "".join(char for char in value if char.isdigit())


def make_detection(
    pii_type: PiiType,
    start: int,
    end: int,
    detector_id: str,
    *,
    confidence: float = 0.95,
) -> Detection:
    return Detection(
        type=pii_type,
        start=start,
        end=end,
        confidence=confidence,
        detector_id=detector_id,
    )


def keyword_distance(
    text: str,
    start: int,
    end: int,
    keywords: tuple[str, ...],
    *,
    window: int = 48,
    whole_word: bool = False,
    side: str = "both",
) -> int | None:
    if side == "left":
        left = max(0, start - window)
        right = start
    elif side == "right":
        left = end
        right = min(len(text), end + window)
    else:
        left = max(0, start - window)
        right = min(len(text), end + window)
    if left >= right:
        return None
    window_text = text[left:right]
    folded = window_text.casefold()
    if len(folded) != len(window_text):
        folded = text.casefold()
        left = max(0, start - window) if side != "right" else end
        right = min(len(folded), end + window) if side != "left" else start
        if side == "left":
            right = start
        elif side == "right":
            left = end
        span_start = start
        span_end = end
        search_from = left
    else:
        span_start = start - left
        span_end = end - left
        search_from = 0
        right = len(folded)
    best: int | None = None
    for keyword in keywords:
        needle = keyword.casefold()
        index = folded.find(needle, search_from, right)
        while index != -1 and index < right:
            keyword_end = index + len(needle)
            absolute = index if len(folded) != len(window_text) else left + index
            if whole_word and not _whole_word(text, absolute, len(needle)):
                index = folded.find(needle, index + 1, right)
                continue
            if keyword_end > span_start and index < span_end:
                distance = 0
            elif keyword_end <= span_start:
                distance = span_start - keyword_end
            else:
                distance = index - span_end
            if best is None or distance < best:
                best = distance
            index = folded.find(needle, index + 1, right)
    return best


def _whole_word(text: str, index: int, length: int) -> bool:
    before = text[index - 1] if index > 0 else ""
    after_index = index + length
    after = text[after_index] if after_index < len(text) else ""
    return not before.isalnum() and not after.isalnum()
