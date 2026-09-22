from datetime import UTC, datetime
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from llm_proxy.masking.base import (
    MaskedEntity,
    OffsetMap,
    normalize_mask_strategy,
    validate_offset_map,
)

SessionEntity = MaskedEntity


class SessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = Field(default=1, gt=0)
    original_text: str
    masked_text: str
    entities: tuple[SessionEntity, ...] = Field(default_factory=tuple)
    offset_map: OffsetMap = Field(default_factory=tuple)
    policy_id: str = Field(min_length=1)
    mask_strategy: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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

    @field_validator("offset_map")
    @classmethod
    def offset_map_must_be_valid(cls, value: OffsetMap) -> OffsetMap:
        return validate_offset_map(value)

    @field_validator("created_at")
    @classmethod
    def created_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def entity_ids_must_be_unique(self) -> Self:
        ids = [entity.stable_entity_id for entity in self.entities]
        if len(ids) != len(set(ids)):
            raise ValueError("stable_entity_id must be unique within a session")
        return self

    def get_entity_by_mask(self, rendered_mask: str) -> SessionEntity | None:
        matches = [entity for entity in self.entities if entity.rendered_mask == rendered_mask]
        if len(matches) != 1:
            return None
        return matches[0]


class StateStore(Protocol):
    async def get(self, key: str) -> SessionRecord | None: ...

    async def create_if_absent(
        self,
        key: str,
        record: SessionRecord,
        ttl_seconds: int,
    ) -> bool: ...

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool: ...

    async def delete(self, key: str) -> bool: ...
