from collections.abc import Sequence

from llm_proxy.detection.models import Detection
from llm_proxy.detection.structured.email import EmailDetector
from llm_proxy.masking.base import (
    MaskContext,
    MaskedEntity,
    MaskResult,
    MaskStrategy,
    apply_replacements,
)


class SimpleEmailDetector(EmailDetector):
    pass


class SimplePlaceholderMaskStrategy(MaskStrategy):
    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult:
        ordered = sorted(detections, key=lambda detection: detection.start)
        entities: list[MaskedEntity] = []

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

        masked = apply_replacements(
            text,
            [
                (
                    detection.start,
                    detection.end,
                    f"[[PII:{detection.type.value.upper()}:{index}]]",
                )
                for index, detection in enumerate(ordered, start=1)
            ],
        )
        return MaskResult(text=masked, entities=tuple(entities))
