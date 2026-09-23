from pydantic import BaseModel, ConfigDict, Field, field_validator

from llm_proxy.detection.models import MANDATORY_PII_TYPES, PiiType, parse_pii_type, parse_pii_types


class ExpectedSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: PiiType
    text: str = Field(min_length=1)
    occurrence: int = Field(default=1, ge=1)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> PiiType:
        return parse_pii_type(value)

    def locate(self, source: str) -> tuple[int, int]:
        start = 0
        found = 0
        while True:
            index = source.find(self.text, start)
            if index < 0:
                raise ValueError(f"{self.text!r} occurrence {self.occurrence} is absent")
            found += 1
            if found == self.occurrence:
                return index, index + len(self.text)
            start = index + 1


class QualityFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    tags: tuple[str, ...] = Field(min_length=1)
    input: str
    expected: tuple[ExpectedSpan, ...] = ()
    enabled_types: tuple[PiiType, ...] = MANDATORY_PII_TYPES
    round_trip: bool = True
    expected_mask: str | None = None

    @field_validator("enabled_types", mode="before")
    @classmethod
    def normalize_enabled_types(cls, value: object) -> tuple[PiiType, ...]:
        return parse_enabled_types(value)

    def resolved_spans(self) -> tuple[tuple[PiiType, int, int], ...]:
        spans = tuple((item.type, *item.locate(self.input)) for item in self.expected)
        for pii_type, _start, _end in spans:
            if pii_type not in self.enabled_types:
                raise ValueError(f"{self.id} expects disabled type {pii_type.value}")
        return spans


def parse_enabled_types(value: object) -> tuple[PiiType, ...]:
    if value is None:
        return MANDATORY_PII_TYPES
    return parse_pii_types(value)
