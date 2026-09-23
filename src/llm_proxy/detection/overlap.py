from collections.abc import Sequence

from llm_proxy.detection.context import Candidate
from llm_proxy.detection.models import Detection


class OverlapResolver:
    def resolve(self, candidates: Sequence[Candidate]) -> tuple[Detection, ...]:
        ranked = sorted(candidates, key=_rank)
        accepted: list[Detection] = []
        for detection, _priority in ranked:
            if any(_overlaps(detection, kept) for kept in accepted):
                continue
            accepted.append(detection)
        accepted.sort(key=lambda detection: (detection.start, detection.end, detection.type.value))
        return tuple(accepted)


def _rank(candidate: Candidate) -> tuple[int, float, int, int, int, str, str]:
    detection, priority = candidate
    return (
        -int(priority),
        -detection.confidence,
        -(detection.end - detection.start),
        detection.start,
        detection.end,
        detection.type.value,
        detection.detector_id,
    )


def _overlaps(left: Detection, right: Detection) -> bool:
    return left.start < right.end and right.start < left.end
