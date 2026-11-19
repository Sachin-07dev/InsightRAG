"""AES-GCM envelope encryption with explicit managed-key integration boundary."""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from insightrag.security.controls import ControlUnavailable


class EncryptionRejected(ValueError):
    """Invalid envelope or authentication failure; never include plaintext/key details."""


class ManagedKeyProvider(Protocol):
    async def wrap_key(self, key_id: str, plaintext_key: bytes, context: bytes) -> bytes: ...

    async def unwrap_key(self, key_id: str, wrapped_key: bytes, context: bytes) -> bytes: ...


@dataclass(frozen=True)
class EncryptedEnvelope:
    version: int
    key_id: str
    nonce: bytes
    ciphertext: bytes
    wrapped_key: bytes


def _context(organization_id: UUID, resource_id: UUID, key_id: str) -> bytes:
    if not isinstance(organization_id, UUID) or not isinstance(resource_id, UUID):
        raise ValueError("Encryption scope must use UUID identities")
    return json.dumps(
        ["insightrag-envelope-v1", str(organization_id), str(resource_id), key_id],
        separators=(",", ":"),
    ).encode()


class EnvelopeCipher:
    def __init__(
        self,
        provider: ManagedKeyProvider | None,
        key_id: str,
        *,
        max_bytes: int = 50 * 1024 * 1024,
        key_timeout_seconds: float = 10,
    ) -> None:
        if not key_id or len(key_id) > 512 or not 1 <= max_bytes <= 50 * 1024 * 1024:
            raise ValueError("Invalid encryption configuration")
        if not 0 < key_timeout_seconds <= 30:
            raise ValueError("Invalid managed-key timeout")
        self.provider, self.key_id, self.max_bytes = provider, key_id, max_bytes
        self.key_timeout_seconds = key_timeout_seconds

    async def encrypt(
        self, organization_id: UUID, resource_id: UUID, plaintext: bytes
    ) -> EncryptedEnvelope:
        if self.provider is None:
            raise ControlUnavailable("Managed key protection is unavailable")
        if not isinstance(plaintext, bytes) or len(plaintext) > self.max_bytes:
            raise EncryptionRejected("Encryption payload exceeds configured limit")
        aad = _context(organization_id, resource_id, self.key_id)
        data_key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
        try:
            async with asyncio.timeout(self.key_timeout_seconds):
                wrapped = await self.provider.wrap_key(self.key_id, data_key, aad)
        except Exception:
            raise ControlUnavailable("Managed key protection is unavailable") from None
        if not isinstance(wrapped, bytes) or not wrapped or len(wrapped) > 16 * 1024:
            raise ControlUnavailable("Managed key protection returned an invalid envelope")
        ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, aad)
        return EncryptedEnvelope(1, self.key_id, nonce, ciphertext, wrapped)

    async def decrypt(
        self, organization_id: UUID, resource_id: UUID, envelope: EncryptedEnvelope
    ) -> bytes:
        if self.provider is None:
            raise ControlUnavailable("Managed key protection is unavailable")
        if (
            type(envelope.version) is not int
            or envelope.version != 1
            or envelope.key_id != self.key_id
            or not isinstance(envelope.nonce, bytes)
            or not isinstance(envelope.ciphertext, bytes)
            or not isinstance(envelope.wrapped_key, bytes)
            or len(envelope.nonce) != 12
            or not 16 <= len(envelope.ciphertext) <= self.max_bytes + 16
            or not 1 <= len(envelope.wrapped_key) <= 16 * 1024
        ):
            raise EncryptionRejected("Invalid encrypted envelope")
        aad = _context(organization_id, resource_id, envelope.key_id)
        try:
            async with asyncio.timeout(self.key_timeout_seconds):
                data_key = await self.provider.unwrap_key(
                    envelope.key_id, envelope.wrapped_key, aad
                )
            if not isinstance(data_key, bytes) or len(data_key) != 32:
                raise ValueError
            return AESGCM(data_key).decrypt(envelope.nonce, envelope.ciphertext, aad)
        except ControlUnavailable:
            raise
        except TimeoutError:
            raise ControlUnavailable("Managed key protection is unavailable") from None
        except Exception:
            raise EncryptionRejected("Encrypted envelope authentication failed") from None


class LocalKeyProvider:
    """Explicit development/test adapter. Production must supply managed KMS integration."""

    def __init__(
        self, key_id: str, key: bytes, *, environment: Literal["development", "test"]
    ) -> None:
        if environment not in ("development", "test") or len(key) != 32 or not key_id:
            raise ValueError(
                "Local key provider is permitted only for explicit development/test use"
            )
        self.key_id, self._key = key_id, key

    def _validate(self, key_id: str) -> None:
        if key_id != self.key_id:
            raise EncryptionRejected("Unknown encryption key")

    async def wrap_key(self, key_id: str, plaintext_key: bytes, context: bytes) -> bytes:
        self._validate(key_id)
        nonce = os.urandom(12)
        return nonce + AESGCM(self._key).encrypt(nonce, plaintext_key, context)

    async def unwrap_key(self, key_id: str, wrapped_key: bytes, context: bytes) -> bytes:
        self._validate(key_id)
        try:
            return AESGCM(self._key).decrypt(wrapped_key[:12], wrapped_key[12:], context)
        except (InvalidTag, ValueError):
            raise EncryptionRejected("Wrapped key authentication failed") from None
