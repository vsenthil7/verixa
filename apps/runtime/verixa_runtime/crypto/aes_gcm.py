"""AES-256-GCM encrypt/decrypt — Replay Vault snapshot encryption.

Per docs/06_data_model/DATA_MODEL.md §6 + docs/11_security_architecture:

- Snapshot bundles are AES-256-GCM encrypted before upload to object store
- Per-tenant data encryption keys (DEK), derived/wrapped under a per-tenant
  key-encryption-key (KEK) held in HashiCorp Vault
- 12-byte nonce per encryption (NIST SP 800-38D recommendation)
- 16-byte authentication tag appended to ciphertext
- Associated data (AD) carries (tenant_id, audit_id, schema_version) so a
  bundle decrypted under the wrong tenant fails authentication

Public API:
  - `AesGcmKey`              — 32-byte AES-256 key (frozen dataclass)
  - `AesGcmCiphertext`       — (nonce, ciphertext_with_tag, associated_data)
  - `AesGcmDecryptionError`  — raised on auth tag failure or input mismatch
  - `generate_key()`         — fresh 32-byte key from CSPRNG
  - `encrypt(key, plaintext, associated_data)` -> AesGcmCiphertext
  - `decrypt(key, ciphertext)` -> bytes
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES: Final[int] = 32  # AES-256
NONCE_BYTES: Final[int] = 12  # NIST SP 800-38D recommendation
TAG_BYTES: Final[int] = 16  # GCM auth tag (appended by AESGCM.encrypt)


class AesGcmDecryptionError(ValueError):
    """Raised when AES-GCM decryption fails (bad tag, wrong key, tamper)."""


@dataclass(frozen=True, slots=True)
class AesGcmKey:
    """A 32-byte AES-256 key."""

    key: bytes

    def __post_init__(self) -> None:
        if len(self.key) != KEY_BYTES:
            raise ValueError(
                f"key must be {KEY_BYTES} bytes (AES-256), "
                f"got {len(self.key)}"
            )


@dataclass(frozen=True, slots=True)
class AesGcmCiphertext:
    """An AES-GCM ciphertext bundle.

    `ciphertext` includes the 16-byte authentication tag appended by AESGCM
    (the cryptography library's convention). To verify integrity, decrypt
    with the original `associated_data`; a tamper anywhere raises
    `AesGcmDecryptionError`.
    """

    nonce: bytes
    ciphertext: bytes  # ciphertext || tag (the cryptography lib glues them)
    associated_data: bytes

    def __post_init__(self) -> None:
        if len(self.nonce) != NONCE_BYTES:
            raise ValueError(
                f"nonce must be {NONCE_BYTES} bytes, got {len(self.nonce)}"
            )
        # Minimum ciphertext is just the tag (when plaintext was empty)
        if len(self.ciphertext) < TAG_BYTES:
            raise ValueError(
                f"ciphertext must be at least {TAG_BYTES} bytes (auth tag); "
                f"got {len(self.ciphertext)}"
            )


def generate_key() -> AesGcmKey:
    """Generate a fresh 32-byte AES-256 key from the OS CSPRNG."""
    return AesGcmKey(key=os.urandom(KEY_BYTES))


def encrypt(
    key: AesGcmKey, plaintext: bytes, associated_data: bytes
) -> AesGcmCiphertext:
    """Encrypt `plaintext` under `key`, binding `associated_data`.

    A fresh 12-byte nonce is generated for each call. **Never** call
    `encrypt` twice with the same key + nonce; AES-GCM catastrophically
    fails authentication under nonce reuse. We don't expose nonce
    selection to callers for that reason.
    """
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError(
            f"plaintext must be bytes-like, got {type(plaintext).__name__}"
        )
    if not isinstance(associated_data, (bytes, bytearray)):
        raise TypeError(
            "associated_data must be bytes-like, got "
            f"{type(associated_data).__name__}"
        )
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(key.key)
    ct_with_tag = aesgcm.encrypt(nonce, bytes(plaintext), bytes(associated_data))
    return AesGcmCiphertext(
        nonce=nonce,
        ciphertext=ct_with_tag,
        associated_data=bytes(associated_data),
    )


def decrypt(key: AesGcmKey, ciphertext: AesGcmCiphertext) -> bytes:
    """Decrypt + verify. Raises `AesGcmDecryptionError` on any failure.

    Failure cases:
      - Wrong key
      - Tampered ciphertext (single bit-flip is enough)
      - Tampered nonce
      - Tampered associated_data
      - Truncated ciphertext (< TAG_BYTES would be rejected at construction)
    """
    aesgcm = AESGCM(key.key)
    try:
        return aesgcm.decrypt(
            ciphertext.nonce,
            ciphertext.ciphertext,
            ciphertext.associated_data,
        )
    except InvalidTag as e:
        raise AesGcmDecryptionError(
            "AES-GCM decryption failed (auth tag mismatch)"
        ) from e
