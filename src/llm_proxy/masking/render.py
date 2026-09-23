from collections.abc import Callable, Sequence

from llm_proxy.detection.models import Detection
from llm_proxy.masking.base import MaskedEntity, MaskResult, apply_replacements

TokenRenderer = Callable[[str, int], str]


def assign_masks(
    text: str,
    detections: Sequence[Detection],
    render: TokenRenderer,
) -> MaskResult:
    ordered = sorted(
        detections,
        key=lambda detection: (detection.start, detection.end, detection.type.value),
    )
    spans = tuple((detection.start, detection.end) for detection in ordered)
    assigned: dict[tuple[str, str], tuple[str, str]] = {}
    occurrences: dict[tuple[str, str], int] = {}
    used_tokens: set[str] = set()
    next_number = 1
    entities: list[MaskedEntity] = []
    replacements: list[tuple[int, int, str]] = []

    for detection in ordered:
        value = text[detection.start : detection.end]
        key = (detection.type.value, value)
        if key not in assigned:
            number = next_number
            token = render(detection.type.value, number)
            while _token_taken(text, spans, token, used_tokens):
                number += 1
                token = render(detection.type.value, number)
            next_number = number + 1
            assigned[key] = (f"{detection.type.value}-{number}", token)
            used_tokens.add(token)
        base_id, token = assigned[key]
        occurrences[key] = occurrences.get(key, 0) + 1
        occurrence = occurrences[key]
        entity_id = base_id if occurrence == 1 else f"{base_id}#{occurrence}"
        entities.append(
            MaskedEntity(
                type=detection.type,
                original_start=detection.start,
                original_end=detection.end,
                rendered_mask=token,
                stable_entity_id=entity_id,
            )
        )
        replacements.append((detection.start, detection.end, token))

    return MaskResult(text=apply_replacements(text, replacements), entities=tuple(entities))


def _token_taken(
    text: str,
    spans: Sequence[tuple[int, int]],
    token: str,
    used_tokens: set[str],
) -> bool:
    if any(token in other or other in token for other in used_tokens):
        return True
    return _occurs_outside(text, token, spans)


def _occurs_outside(text: str, token: str, spans: Sequence[tuple[int, int]]) -> bool:
    start = 0
    while True:
        index = text.find(token, start)
        if index < 0:
            return False
        end = index + len(token)
        inside = any(span_start <= index and end <= span_end for span_start, span_end in spans)
        if not inside:
            return True
        start = index + 1
