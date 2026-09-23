from collections.abc import Sequence

from llm_proxy.detection.models import Detection
from llm_proxy.masking.base import MaskContext, MaskResult
from llm_proxy.masking.render import assign_masks


class PlaceholderMaskStrategy:
    """Internal product placeholders. Not an official Alfa mask format."""

    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult:
        del context
        return assign_masks(text, detections, _placeholder_token)


def _placeholder_token(pii_type: str, number: int) -> str:
    return f"[[PII:{pii_type.upper()}:{number}]]"
