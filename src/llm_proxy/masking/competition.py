from collections.abc import Sequence

from llm_proxy.detection.models import Detection
from llm_proxy.masking.base import MaskContext, MaskResult
from llm_proxy.masking.render import assign_masks


class CompetitionMaskStrategy:
    """Reversible local token used until an official mask sample exists.

    ``<TYPE_n>`` matches the shape of the non-canonical illustration in
    requirements §5.1. It is not a confirmed scoring format.
    """

    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult:
        del context
        return assign_masks(text, detections, _competition_token)


def _competition_token(pii_type: str, number: int) -> str:
    return f"<{pii_type.upper()}_{number}>"
