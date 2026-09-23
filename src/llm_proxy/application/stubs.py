import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, Detector, PiiType
from llm_proxy.masking.base import MaskContext, MaskedEntity, MaskResult, MaskStrategy

_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


class SimpleEmailDetector(Detector):
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.EMAIL not in enabled_types:
            return ()
        return tuple(
            Detection(
                type=PiiType.EMAIL,
                start=match.start(),
                end=match.end(),
                confidence=1.0,
                detector_id="simple-email",
            )
            for match in _EMAIL_PATTERN.finditer(text)
        )


class SimplePlaceholderMaskStrategy(MaskStrategy):
    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult:
        ordered = sorted(detections, key=lambda detection: detection.start)
        entities: list[MaskedEntity] = []
        masked = text

        for index, detection in enumerate(ordered, start=1):
            rendered_mask = f"[[PII:{detection.type.value.upper()}:{index}]]"
            entities.append(
                MaskedEntity(
                    type=detection.type,
                    original_start=detection.start,
                    original_end=detection.end,
                    rendered_mask=rendered_mask,
                    stable_entity_id=f"{detection.type.value}-{index}",
                )
            )

        for detection in reversed(ordered):
            index = ordered.index(detection) + 1
            rendered_mask = f"[[PII:{detection.type.value.upper()}:{index}]]"
            masked = masked[: detection.start] + rendered_mask + masked[detection.end :]

        return MaskResult(text=masked, entities=tuple(entities))
