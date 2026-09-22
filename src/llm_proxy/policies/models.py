from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from llm_proxy.detection.models import (
    PiiType,
    parse_pii_types,
)
from llm_proxy.masking.base import normalize_mask_strategy


class ConsumerPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    enabled: bool
    pii_types: tuple[PiiType, ...]
    allow_demask: bool
    mask_strategy: str = Field(min_length=1)

    @field_validator("policy_id", "system_id")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("pii_types", mode="before")
    @classmethod
    def normalize_pii_types(cls, value: object) -> tuple[PiiType, ...]:
        return parse_pii_types(value)

    @field_validator("mask_strategy", mode="before")
    @classmethod
    def normalize_mask_strategy_value(cls, value: object) -> str:
        return normalize_mask_strategy(value)

    @model_validator(mode="after")
    def pii_types_must_be_unique(self) -> Self:
        if len(self.pii_types) != len(set(self.pii_types)):
            raise ValueError("pii_types must not contain duplicates")
        return self


class ConsumerContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    consumer_id: str = Field(min_length=1)
    policy: ConsumerPolicy


class ConsumerResolver(Protocol):
    def resolve(self, consumer_id: str) -> ConsumerContext: ...


class PolicyRegistry(Protocol):
    def get(self, system_id: str) -> ConsumerPolicy | None: ...

    def require(self, system_id: str) -> ConsumerPolicy: ...
