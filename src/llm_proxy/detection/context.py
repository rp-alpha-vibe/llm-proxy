from collections.abc import Sequence

from llm_proxy.detection.models import Detection
from llm_proxy.detection.registry import DetectorPriority

_ANCHOR_WINDOW = 40
Candidate = tuple[Detection, DetectorPriority]


class ContextResolver:
    def resolve(self, text: str, candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
        confirmed: list[Candidate] = []
        for detection, priority in candidates:
            if priority is DetectorPriority.STRUCTURED:
                confirmed.append((detection, priority))
                continue
            if not _has_context(text, detection):
                continue
            confirmed.append((detection, DetectorPriority.CONTEXT))
        return tuple(confirmed)


def _has_context(text: str, detection: Detection) -> bool:
    anchor = detection.metadata.get("context_anchor")
    if isinstance(anchor, str) and anchor:
        window_start = max(0, detection.start - _ANCHOR_WINDOW)
        window_end = min(len(text), detection.end + _ANCHOR_WINDOW)
        return anchor.casefold() in text[window_start:window_end].casefold()
    return detection.metadata.get("context_confirmed") is True
