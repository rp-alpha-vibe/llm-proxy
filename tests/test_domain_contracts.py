from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from llm_proxy.detection.models import (
    MANDATORY_PII_TYPES,
    Detection,
    Detector,
    PiiType,
    parse_pii_type,
    parse_pii_types,
)
from llm_proxy.masking.base import (
    MaskContext,
    MaskedEntity,
    MaskResult,
    MaskStrategy,
)
from llm_proxy.policies.models import (
    ConsumerContext,
    ConsumerPolicy,
    ConsumerResolver,
    PolicyRegistry,
)
from llm_proxy.state.models import SessionRecord, StateStore

EXPECTED_MANDATORY_TYPES = frozenset(
    {
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
    }
)


def test_mandatory_pii_types_cover_all_required_categories() -> None:
    assert frozenset(MANDATORY_PII_TYPES) == EXPECTED_MANDATORY_TYPES
    assert len(MANDATORY_PII_TYPES) == len(set(MANDATORY_PII_TYPES))


def test_pii_type_aliases_normalize_to_canonical_values() -> None:
    assert parse_pii_type("FIO") == PiiType.PERSON
    assert parse_pii_type("passport_series_number") == PiiType.PASSPORT
    assert parse_pii_type("PAN") == PiiType.PAYMENT_CARD
    assert parse_pii_type("CVC") == PiiType.CVV

    assert parse_pii_types(["FULL_NAME", "DATE_OF_BIRTH", "PAN", "CVC"]) == (
        PiiType.PERSON,
        PiiType.BIRTH_DATE,
        PiiType.PAYMENT_CARD,
        PiiType.CVV,
    )
    assert parse_pii_types("all") == MANDATORY_PII_TYPES


def test_detection_validates_and_round_trips_json() -> None:
    detection = Detection.model_validate(
        {
            "type": "FIO",
            "start": 0,
            "end": 13,
            "confidence": 0.99,
            "detector_id": "synthetic-person-rule",
            "metadata": {"context": "synthetic"},
        }
    )

    assert detection.type == PiiType.PERSON
    assert Detection.model_validate_json(detection.model_dump_json()) == detection


def test_detection_rejects_invalid_spans_and_types() -> None:
    with pytest.raises(ValidationError):
        Detection(
            type=PiiType.PERSON,
            start=4,
            end=2,
            confidence=1.0,
            detector_id="synthetic-person-rule",
        )

    with pytest.raises(ValidationError):
        Detection.model_validate(
            {
                "type": "unknown",
                "start": 0,
                "end": 1,
                "confidence": 1.0,
                "detector_id": "synthetic-person-rule",
            }
        )


def test_mask_models_validate_offsets_and_unique_entities() -> None:
    entity = MaskedEntity(
        type=PiiType.PERSON,
        original_start=0,
        original_end=13,
        rendered_mask="[[PII:PERSON:1]]",
        stable_entity_id="entity-1",
    )
    result = MaskResult(
        text="synthetic-name",
        entities=(entity,),
        offset_map=((0, 0), (13, 18)),
    )

    assert MaskResult.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        MaskResult(
            text="synthetic-name",
            entities=(entity, entity),
            offset_map=((0, 0), (13, 18)),
        )
    with pytest.raises(ValidationError):
        MaskResult(text="synthetic-name", offset_map=((1, 0), (0, 1)))


def test_session_record_round_trips_and_looks_up_unique_mask() -> None:
    entity = MaskedEntity(
        type=PiiType.PERSON,
        original_start=0,
        original_end=13,
        rendered_mask="[[PII:PERSON:1]]",
        stable_entity_id="entity-1",
    )
    record = SessionRecord(
        original_text="synthetic-name",
        masked_text="[[PII:PERSON:1]]",
        entities=(entity,),
        offset_map=((0, 0), (13, 18)),
        policy_id="policy-1",
        mask_strategy="placeholder",
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    assert SessionRecord.model_validate_json(record.model_dump_json()) == record
    assert record.get_entity_by_mask("[[PII:PERSON:1]]") == entity
    assert record.get_entity_by_mask("[[PII:UNKNOWN:1]]") is None


def test_session_record_rejects_duplicate_entities_and_naive_time() -> None:
    entity = MaskedEntity(
        type=PiiType.PERSON,
        original_start=0,
        original_end=13,
        rendered_mask="[[PII:PERSON:1]]",
        stable_entity_id="entity-1",
    )

    with pytest.raises(ValidationError):
        SessionRecord(
            original_text="synthetic-name",
            masked_text="[[PII:PERSON:1]]",
            entities=(entity, entity),
            policy_id="policy-1",
            mask_strategy="placeholder",
        )

    with pytest.raises(ValidationError):
        SessionRecord(
            original_text="synthetic-name",
            masked_text="[[PII:PERSON:1]]",
            policy_id="policy-1",
            mask_strategy="placeholder",
            created_at=datetime(2026, 1, 2, 3, 4, 5),
        )


def test_consumer_policy_normalizes_types_and_strategy() -> None:
    policy = ConsumerPolicy.model_validate(
        {
            "policy_id": "policy-1",
            "system_id": "consumer-1",
            "enabled": True,
            "pii_types": ["FIO", "EMAIL", "PAN"],
            "allow_demask": True,
            "mask_strategy": "PLACEHOLDER",
        }
    )

    assert policy.pii_types == (
        PiiType.PERSON,
        PiiType.EMAIL,
        PiiType.PAYMENT_CARD,
    )
    assert policy.mask_strategy == "placeholder"
    assert ConsumerPolicy.model_validate_json(policy.model_dump_json()) == policy


def test_consumer_policy_rejects_duplicates_unknown_strategy_and_blank_ids() -> None:
    with pytest.raises(ValidationError):
        ConsumerPolicy(
            policy_id="policy-1",
            system_id="consumer-1",
            enabled=True,
            pii_types=(PiiType.PERSON, PiiType.FIO),
            allow_demask=True,
            mask_strategy="placeholder",
        )

    with pytest.raises(ValidationError):
        ConsumerPolicy(
            policy_id="policy-1",
            system_id="consumer-1",
            enabled=True,
            pii_types=(PiiType.EMAIL,),
            allow_demask=True,
            mask_strategy="unknown",
        )

    with pytest.raises(ValidationError):
        ConsumerPolicy(
            policy_id=" ",
            system_id="consumer-1",
            enabled=True,
            pii_types=(PiiType.EMAIL,),
            allow_demask=True,
            mask_strategy="placeholder",
        )

    with pytest.raises(ValidationError, match="enabled policy must declare pii_types"):
        ConsumerPolicy(
            policy_id="policy-1",
            system_id="consumer-1",
            enabled=True,
            pii_types=(),
            allow_demask=True,
            mask_strategy="placeholder",
        )

    disabled = ConsumerPolicy(
        policy_id="policy-1",
        system_id="consumer-1",
        enabled=False,
        pii_types=(),
        allow_demask=False,
        mask_strategy="placeholder",
    )
    assert disabled.pii_types == ()


def test_consumer_context_rejects_blank_and_mismatched_ids() -> None:
    policy = ConsumerPolicy(
        policy_id="policy-1",
        system_id="consumer-1",
        enabled=True,
        pii_types=(PiiType.EMAIL,),
        allow_demask=True,
        mask_strategy="placeholder",
    )

    with pytest.raises(ValidationError, match="consumer_id must not be blank"):
        ConsumerContext(consumer_id="   ", policy=policy)

    with pytest.raises(ValidationError, match=r"consumer_id must match policy\.system_id"):
        ConsumerContext(consumer_id="other", policy=policy)


def test_consumer_context_and_domain_protocols_are_defined() -> None:
    policy = ConsumerPolicy(
        policy_id="policy-1",
        system_id="consumer-1",
        enabled=True,
        pii_types=(PiiType.EMAIL,),
        allow_demask=True,
        mask_strategy="placeholder",
    )
    context = ConsumerContext(consumer_id="consumer-1", policy=policy)

    assert context.consumer_id == "consumer-1"
    assert context.policy == policy
    assert all(
        getattr(protocol, "_is_protocol", False)
        for protocol in (
            Detector,
            MaskStrategy,
            StateStore,
            ConsumerResolver,
            PolicyRegistry,
        )
    )


def test_mask_context_rejects_unknown_strategy() -> None:
    with pytest.raises(ValidationError):
        MaskContext(policy_id="policy-1", mask_strategy="unknown")
