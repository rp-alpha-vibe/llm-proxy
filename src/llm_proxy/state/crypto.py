import os
import struct
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr, ValidationError

from .models import SessionRecord

_ENVELOPE_VERSION: Final = 1
_NONCE_SIZE: Final = 12
_HEADER = struct.Struct(">BI")
_AAD_PREFIX = b"llm-proxy:SessionRecord:v1"


class StateEncryptionError(ValueError):
    pass


class StateEncryptionKeyError(StateEncryptionError):
    pass


class StateDecryptionError(StateEncryptionError):
    pass


def _key_bytes(encryption_key: SecretStr) -> bytes:
    key = encryption_key.get_secret_value().encode("utf-8")
    if len(key) not in (16, 24, 32):
        raise StateEncryptionKeyError("encryption key must contain 16, 24, or 32 bytes")
    return key


class SessionRecordCodec:
    def __init__(self, encryption_key: SecretStr) -> None:
        self._encryption_key = _key_bytes(encryption_key)

    def __repr__(self) -> str:
        return "<SessionRecordCodec>"

    @staticmethod
    def _associated_data(redis_key: str, record_version: int) -> bytes:
        return (
            _AAD_PREFIX
            + b"\0"
            + redis_key.encode("utf-8")
            + b"\0"
            + struct.pack(">I", record_version)
        )

    def encrypt(self, redis_key: str, record: SessionRecord) -> bytes:
        if not redis_key:
            raise ValueError("redis_key must not be empty")

        nonce = os.urandom(_NONCE_SIZE)
        plaintext = record.model_dump_json().encode("utf-8")
        associated_data = self._associated_data(redis_key, record.version)
        ciphertext = AESGCM(self._encryption_key).encrypt(
            nonce,
            plaintext,
            associated_data,
        )
        return _HEADER.pack(_ENVELOPE_VERSION, record.version) + nonce + ciphertext

    def decrypt(self, redis_key: str, payload: bytes) -> SessionRecord:
        if len(payload) < _HEADER.size + _NONCE_SIZE + 16:
            raise StateDecryptionError("session record payload is too short")
        if not redis_key:
            raise ValueError("redis_key must not be empty")

        envelope_version, record_version = _HEADER.unpack_from(payload)
        if envelope_version != _ENVELOPE_VERSION:
            raise StateDecryptionError("unsupported session record envelope version")

        nonce_start = _HEADER.size
        nonce_end = nonce_start + _NONCE_SIZE
        nonce = payload[nonce_start:nonce_end]
        ciphertext = payload[nonce_end:]
        associated_data = self._associated_data(redis_key, record_version)

        try:
            plaintext = AESGCM(self._encryption_key).decrypt(
                nonce,
                ciphertext,
                associated_data,
            )
        except InvalidTag as exc:
            raise StateDecryptionError("session record authentication failed") from exc

        try:
            record = SessionRecord.model_validate_json(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, ValidationError) as exc:
            raise StateDecryptionError("invalid session record payload") from exc

        if record.version != record_version:
            raise StateDecryptionError("session record version mismatch")
        return record
