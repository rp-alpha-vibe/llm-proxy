from collections.abc import Mapping, Sequence

from llm_proxy.detection.models import Detection
from llm_proxy.masking.base import MaskContext, MaskResult, MaskStrategy


class RoutingMaskStrategy:
    def __init__(self, strategies: Mapping[str, MaskStrategy]) -> None:
        if not strategies:
            raise ValueError("at least one mask strategy is required")
        self._strategies = dict(strategies)

    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult:
        strategy = self._strategies.get(context.mask_strategy)
        if strategy is None:
            raise ValueError(f"unknown mask strategy: {context.mask_strategy}")
        return strategy.mask(text, detections, context)
