from collections.abc import Collection, Iterable, Sequence
from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PiiType(StrEnum):
    PERSON = "person"
    FIO = "person"
    FULL_NAME = "person"
    PERSON_NAME = "person"
    BIRTH_DATE = "birth_date"
    DATE_OF_BIRTH = "birth_date"
    BIRTH_PLACE = "birth_place"
    PLACE_OF_BIRTH = "birth_place"
    PASSPORT = "passport"
    PASSPORT_SERIES_NUMBER = "passport"
    PASSPORT_SERIES = "passport"
    PASSPORT_NUMBER = "passport"
    CITIZENSHIP = "citizenship"
    PASSPORT_ISSUER = "passport_issuer"
    PASSPORT_ISSUING_AUTHORITY = "passport_issuer"
    PASSPORT_DIVISION_CODE = "passport_division_code"
    PASSPORT_UNIT_CODE = "passport_division_code"
    PASSPORT_ISSUE_DATE = "passport_issue_date"
    DRIVER_LICENSE = "driver_license"
    DRIVER_LICENSE_SERIES_NUMBER = "driver_license"
    DRIVER_LICENSE_NUMBER = "driver_license"
    ADDRESS = "address"
    ADDRESS_COUNTRY = "address_country"
    ADDRESS_REGION = "address_region"
    ADDRESS_DISTRICT = "address_district"
    ADDRESS_CITY = "address_city"
    ADDRESS_STREET = "address_street"
    ADDRESS_BUILDING = "address_house"
    ADDRESS_HOUSE = "address_house"
    ADDRESS_UNIT = "address_apartment"
    ADDRESS_APARTMENT = "address_apartment"
    ADDRESS_POSTAL_CODE = "address_postal_code"
    ADDRESS_ZIP = "address_postal_code"
    ADDRESS_POSTCODE = "address_postal_code"
    EMAIL = "email"
    PHONE = "phone"
    INN = "inn"
    TAX_ID = "inn"
    PAYMENT_CARD = "card"
    CARD = "card"
    BANK_CARD = "card"
    PAN = "card"
    CARD_NUMBER = "card"
    CVV = "cvv"
    CVC = "cvv"
    PIN = "pin"
    CARDHOLDER = "cardholder"
    CARDHOLDER_NAME = "cardholder"
    CARD_HOLDER = "cardholder"


MANDATORY_PII_TYPES: tuple[PiiType, ...] = (
    PiiType.PERSON,
    PiiType.BIRTH_DATE,
    PiiType.BIRTH_PLACE,
    PiiType.PASSPORT,
    PiiType.CITIZENSHIP,
    PiiType.PASSPORT_ISSUER,
    PiiType.PASSPORT_DIVISION_CODE,
    PiiType.PASSPORT_ISSUE_DATE,
    PiiType.DRIVER_LICENSE,
    PiiType.ADDRESS,
    PiiType.ADDRESS_COUNTRY,
    PiiType.ADDRESS_REGION,
    PiiType.ADDRESS_DISTRICT,
    PiiType.ADDRESS_CITY,
    PiiType.ADDRESS_STREET,
    PiiType.ADDRESS_BUILDING,
    PiiType.ADDRESS_UNIT,
    PiiType.ADDRESS_POSTAL_CODE,
    PiiType.EMAIL,
    PiiType.PHONE,
    PiiType.INN,
    PiiType.PAYMENT_CARD,
    PiiType.CVV,
    PiiType.PIN,
    PiiType.CARDHOLDER,
)
REQUIRED_PII_TYPES = MANDATORY_PII_TYPES

_PII_TYPE_NAMES = {
    name.casefold(): PiiType(member.value) for name, member in PiiType.__members__.items()
}
_PII_TYPE_VALUES = {member.value.casefold(): PiiType(member.value) for member in PiiType}


def parse_pii_type(value: object) -> PiiType:
    if isinstance(value, PiiType):
        return PiiType(value.value)

    if not isinstance(value, str):
        raise ValueError("pii type must be a PiiType or string")

    key = value.strip().casefold()
    if not key:
        raise ValueError("pii type must not be blank")

    member = _PII_TYPE_NAMES.get(key) or _PII_TYPE_VALUES.get(key)
    if member is None:
        raise ValueError("unknown PII type")
    return member


def parse_pii_types(value: object) -> tuple[PiiType, ...]:
    if isinstance(value, PiiType):
        return (PiiType(value.value),)

    if isinstance(value, str):
        if value.strip().casefold() == "all":
            return MANDATORY_PII_TYPES
        return (parse_pii_type(value),)

    if not isinstance(value, Iterable) or isinstance(value, (bytes, bytearray)):
        raise ValueError("pii_types must be a PiiType, string, or iterable")

    try:
        items = list(value)
    except TypeError as exc:
        raise ValueError("pii_types must be a PiiType, string, or iterable") from exc

    if any(isinstance(item, str) and item.strip().casefold() == "all" for item in items):
        if len(items) != 1:
            raise ValueError("all cannot be combined with individual PII types")
        return MANDATORY_PII_TYPES

    return tuple(parse_pii_type(item) for item in items)


class Detection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: PiiType
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    detector_id: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> PiiType:
        return parse_pii_type(value)

    @field_validator("detector_id")
    @classmethod
    def detector_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("detector_id must not be blank")
        return value

    @model_validator(mode="after")
    def span_must_be_valid(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class Detector(Protocol):
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]: ...
