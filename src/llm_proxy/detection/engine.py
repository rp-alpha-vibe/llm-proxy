from collections.abc import Collection, Sequence

from llm_proxy.detection.context import Candidate, ContextResolver
from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.overlap import OverlapResolver
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.text_view import TextView


class PiiEngine:
    def __init__(
        self,
        registry: DetectorRegistry,
        *,
        context_resolver: ContextResolver | None = None,
        overlap_resolver: OverlapResolver | None = None,
    ) -> None:
        self._registry = registry
        self._context_resolver = context_resolver or ContextResolver()
        self._overlap_resolver = overlap_resolver or OverlapResolver()

    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if not isinstance(text, str):
            raise TypeError("text must be a string")

        enabled = frozenset(enabled_types)
        if not enabled:
            return ()

        view = TextView.from_text(text)
        candidates: list[Candidate] = []
        for registration in self._registry.for_types(enabled):
            found = registration.detector.detect(view.normalized, enabled)
            for detection in found:
                if detection.type not in enabled or detection.type not in registration.types:
                    continue
                start, end = view.to_original_span(detection.start, detection.end)
                if start != detection.start or end != detection.end:
                    detection = detection.model_copy(update={"start": start, "end": end})
                candidates.append((detection, registration.priority))

        confirmed = self._context_resolver.resolve(view.original, candidates)
        return self._overlap_resolver.resolve(confirmed)
