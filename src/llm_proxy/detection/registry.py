from collections.abc import Collection
from dataclasses import dataclass
from enum import IntEnum

from llm_proxy.detection.models import Detector, PiiType


class DetectorPriority(IntEnum):
    GENERIC = 1
    CONTEXT = 2
    STRUCTURED = 3


@dataclass(frozen=True, slots=True)
class DetectorRegistration:
    detector: Detector
    types: frozenset[PiiType]
    priority: DetectorPriority


class DetectorRegistry:
    def __init__(self) -> None:
        self._registrations: list[DetectorRegistration] = []

    def register(
        self,
        detector: Detector,
        *,
        types: Collection[PiiType],
        priority: DetectorPriority,
    ) -> None:
        declared = frozenset(types)
        if not declared:
            raise ValueError("detector must declare at least one PII type")
        if any(not isinstance(pii_type, PiiType) for pii_type in declared):
            raise TypeError("detector types must be PiiType values")
        self._registrations.append(DetectorRegistration(detector, declared, priority))

    def for_types(self, enabled_types: Collection[PiiType]) -> tuple[DetectorRegistration, ...]:
        enabled = frozenset(enabled_types)
        if not enabled:
            return ()
        return tuple(item for item in self._registrations if item.types & enabled)
