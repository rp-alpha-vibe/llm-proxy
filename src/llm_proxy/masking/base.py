from collections.abc import Sequence
from enum import StrEnum
from itertools import pairwise
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from llm_proxy.detection.models import Detection, PiiType, parse_pii_type

OffsetMap = tuple[tuple[int, int], ...]


def validate_offset_map(value: OffsetMap) -> OffsetMap:
    if any(original < 0 or normalized < 0 for original, normalized in value):
        raise ValueError("offset_map values must be non-negative")
    if any(
        current[0] <= previous[0] or current[1] < previous[1]
        for previous, current in pairwise(value)
    ):
        raise ValueError("offset_map must be ordered")
    return value


class MaskStrategyName(StrEnum):
    COMPETITION = "competition"
    PLACEHOLDER = "placeholder"


SUPPORTED_MASK_STRATEGIES = frozenset(strategy.value for strategy in MaskStrategyName)


def normalize_mask_strategy(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("mask_strategy must be a string")

    normalized = value.strip().casefold()
    if normalized not in SUPPORTED_MASK_STRATEGIES:
        raise ValueError(f"unknown mask strategy: {value!r}")
    return normalized


class MaskContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str = Field(min_length=1)
    mask_strategy: str = Field(min_length=1)

    @field_validator("policy_id")
    @classmethod
    def policy_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("policy_id must not be blank")
        return value

    @field_validator("mask_strategy", mode="before")
    @classmethod
    def normalize_mask_strategy_value(cls, value: object) -> str:
        return normalize_mask_strategy(value)


class MaskedEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: PiiType
    original_start: int = Field(ge=0)
    original_end: int = Field(gt=0)
    rendered_mask: str = Field(min_length=1)
    stable_entity_id: str = Field(min_length=1)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> PiiType:
        return parse_pii_type(value)

    @field_validator("rendered_mask", "stable_entity_id")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mask identifiers must not be blank")
        return value

    @model_validator(mode="after")
    def span_must_be_valid(self) -> Self:
        if self.original_end <= self.original_start:
            raise ValueError("original_end must be greater than original_start")
        return self


class MaskResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    entities: tuple[MaskedEntity, ...] = Field(default_factory=tuple)
    offset_map: OffsetMap = Field(default_factory=tuple)

    @field_validator("offset_map")
    @classmethod
    def offset_map_must_be_valid(cls, value: OffsetMap) -> OffsetMap:
        return validate_offset_map(value)

    @model_validator(mode="after")
    def entity_ids_must_be_unique(self) -> Self:
        ids = [entity.stable_entity_id for entity in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("stable_entity_id must be unique within a mask result")
        return self


class MaskStrategy(Protocol):
    def mask(
        self,
        text: str,
        detections: Sequence[Detection],
        context: MaskContext,
    ) -> MaskResult: ...
