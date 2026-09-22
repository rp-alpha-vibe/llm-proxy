from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from llm_proxy.detection.models import PiiType
from llm_proxy.masking.base import MaskedEntity
from llm_proxy.state.crypto import (
    SessionRecordCodec,
    StateDecryptionError,
    StateEncryptionKeyError,
)
from llm_proxy.state.models import SessionRecord


def make_record() -> SessionRecord:
    entity = MaskedEntity(
        type=PiiType.PERSON,
        original_start=0,
        original_end=13,
        rendered_mask="[[PII:PERSON:1]]",
        stable_entity_id="entity-1",
    )
    return SessionRecord(
        original_text="synthetic-name",
        masked_text="[[PII:PERSON:1]]",
        entities=(entity,),
        policy_id="policy-1",
        mask_strategy="placeholder",
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def test_session_record_codec_round_trips_encrypted_payload() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    record = make_record()

    payload = codec.encrypt("session:consumer:payload-hash", record)

    assert codec.decrypt("session:consumer:payload-hash", payload) == record


def test_session_record_ciphertext_does_not_contain_plaintext() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    record = make_record()

    payload = codec.encrypt("session:consumer:payload-hash", record)

    for sensitive_value in (
        record.original_text,
        record.masked_text,
        record.entities[0].rendered_mask,
        record.entities[0].stable_entity_id,
    ):
        assert sensitive_value.encode("utf-8") not in payload


def test_session_record_codec_uses_a_fresh_nonce() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    record = make_record()

    first = codec.encrypt("session:consumer:payload-hash", record)
    second = codec.encrypt("session:consumer:payload-hash", record)

    assert first[5:17] != second[5:17]
    assert first != second


def test_session_record_codec_rejects_wrong_key_redis_key_and_tampering() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))
    other_codec = SessionRecordCodec(SecretStr("abcdef0123456789abcdef0123456789"))
    record = make_record()
    payload = codec.encrypt("session:consumer:payload-hash", record)

    with pytest.raises(StateDecryptionError):
        other_codec.decrypt("session:consumer:payload-hash", payload)
    with pytest.raises(StateDecryptionError):
        codec.decrypt("session:other:payload-hash", payload)

    tampered = bytearray(payload)
    tampered[-1] ^= 1
    with pytest.raises(StateDecryptionError):
        codec.decrypt("session:consumer:payload-hash", bytes(tampered))


def test_session_record_codec_rejects_short_payload_and_invalid_key() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))

    with pytest.raises(StateDecryptionError):
        codec.decrypt("session:consumer:payload-hash", b"short")
    with pytest.raises(StateEncryptionKeyError):
        SessionRecordCodec(SecretStr("short"))


def test_session_record_codec_repr_does_not_expose_key() -> None:
    codec = SessionRecordCodec(SecretStr("0123456789abcdef0123456789abcdef"))

    assert "0123456789" not in repr(codec)
