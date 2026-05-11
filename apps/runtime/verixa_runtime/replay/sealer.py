"""Replay Vault encryption + content-addressable key derivation (CP-12.2).

Ties three CP-4 primitives together:

  - canonicalise_bundle (CP-12.1) -> deterministic plaintext bytes
  - AES-256-GCM encrypt (CP-4 crypto.aes_gcm) -> ciphertext + tag
  - SHA-256 of (nonce || ciphertext || associated_data) ->
    content-addressable storage key

The pair of functions exposed here -- ``encrypt_bundle`` and
``decrypt_bundle`` -- are the entire crypto surface CP-12.4
snapshotter / reconstructor needs. The object-store abstraction
(CP-12.3) is a separate concern and doesn't see plaintext.

Per-tenant erasure (GDPR Article 17): the tenant's AES-256 key lives
under their KEK in Vault; zeroising the KEK renders every encrypted
bundle for that tenant cryptographically unrecoverable. The
encrypted bytes can remain in the object store as audit artefacts
(the *fact* that a decision was made survives) while the plaintext
content is gone.

Associated data is structural -- (tenant_id, audit_id,
schema_version). A bundle encrypted under tenant A with audit_id X
cannot be decrypted under tenant A with audit_id Y; the AD
mismatch fails the auth tag check. This pins each ciphertext to
its exact context.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from verixa_runtime.crypto.aes_gcm import (
    AesGcmCiphertext,
    AesGcmDecryptionError,
    AesGcmKey,
)
from verixa_runtime.crypto.aes_gcm import (
    decrypt as aes_decrypt,
)
from verixa_runtime.crypto.aes_gcm import (
    encrypt as aes_encrypt,
)
from verixa_runtime.replay.bundle import (
    ReplayBundle,
    canonicalise_bundle,
    deserialise_bundle,
)

# Length of the content-addressable storage key (hex of SHA-256).
STORAGE_KEY_HEX_LEN: Final[int] = 64


@dataclass(frozen=True, slots=True)
class EncryptedBundle:
    """An AES-GCM-sealed ReplayBundle ready for object-store upload.

    ``storage_key`` is SHA-256(nonce || ciphertext || AD) in lowercase
    hex -- 64 chars. Same input bytes always produce the same storage
    key (content-addressable), so a repeated snapshot of the exact
    same decision context lands on the same object key and the store
    deduplicates naturally.

    NOTE: because AES-GCM uses a fresh random nonce per call, two
    encryptions of the *same plaintext* produce different ciphertexts
    and therefore different storage_keys. Determinism here is over the
    *ciphertext + nonce + AD triple*, not over the plaintext.
    """

    ciphertext: AesGcmCiphertext
    storage_key: str
    tenant_id: uuid.UUID
    audit_id: uuid.UUID

    def __post_init__(self) -> None:
        if len(self.storage_key) != STORAGE_KEY_HEX_LEN:
            raise ValueError(
                f"storage_key must be {STORAGE_KEY_HEX_LEN} hex chars; "
                f"got {len(self.storage_key)}"
            )
        if not all(c in "0123456789abcdef" for c in self.storage_key):
            raise ValueError(
                f"storage_key must be lowercase hex; got {self.storage_key!r}"
            )


def _build_associated_data(
    tenant_id: uuid.UUID, audit_id: uuid.UUID, schema_version: int
) -> bytes:
    """Deterministic AD bytes pinning ciphertext to its context.

    Format: canonical JSON {audit_id, schema_version, tenant_id}
    sorted-keys minimal-separators UTF-8. Including schema_version
    means a version-1 bundle can never be decrypted as if it were
    version-2 (the AD mismatch would fail the auth tag).
    """
    payload = {
        "tenant_id": str(tenant_id),
        "audit_id": str(audit_id),
        "schema_version": schema_version,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _content_address(
    ciphertext: AesGcmCiphertext,
) -> str:
    """SHA-256(nonce || ciphertext || associated_data) lowercase hex."""
    h = sha256()
    h.update(ciphertext.nonce)
    h.update(ciphertext.ciphertext)
    h.update(ciphertext.associated_data)
    return h.hexdigest()


def encrypt_bundle(
    bundle: ReplayBundle, key: AesGcmKey
) -> EncryptedBundle:
    """Canonicalise + AES-256-GCM encrypt + derive storage key.

    Raises nothing the caller wouldn't already get from the underlying
    primitives (ValueError on malformed key, etc).
    """
    plaintext = canonicalise_bundle(bundle)
    ad = _build_associated_data(
        bundle.tenant_id, bundle.audit_id, bundle.schema_version
    )
    ciphertext = aes_encrypt(key, plaintext, ad)
    storage_key = _content_address(ciphertext)
    return EncryptedBundle(
        ciphertext=ciphertext,
        storage_key=storage_key,
        tenant_id=bundle.tenant_id,
        audit_id=bundle.audit_id,
    )


def decrypt_bundle(
    encrypted: EncryptedBundle, key: AesGcmKey
) -> ReplayBundle:
    """Inverse of encrypt_bundle.

    Raises AesGcmDecryptionError if the auth tag fails (wrong key,
    tampered ciphertext, tampered AD, or AD reconstructed wrong).
    Raises ValueError if the decrypted plaintext doesn't parse as a
    bundle (would indicate a corrupted ciphertext that nonetheless
    happened to authenticate -- impossible under AES-GCM with the
    correct key, but we still verify the inverse holds).
    """
    plaintext = aes_decrypt(key, encrypted.ciphertext)
    bundle = deserialise_bundle(plaintext)
    # Defense-in-depth: bundle.tenant_id / audit_id MUST match the
    # EncryptedBundle's labels. If they don't, something has gone
    # very wrong (the AD authenticated but the plaintext somehow
    # disagrees -- protocol bug, not crypto bug).
    if bundle.tenant_id != encrypted.tenant_id:
        raise ValueError(
            f"decrypted bundle tenant_id {bundle.tenant_id} does not "
            f"match EncryptedBundle.tenant_id {encrypted.tenant_id}"
        )
    if bundle.audit_id != encrypted.audit_id:
        raise ValueError(
            f"decrypted bundle audit_id {bundle.audit_id} does not "
            f"match EncryptedBundle.audit_id {encrypted.audit_id}"
        )
    return bundle


__all__ = [
    "STORAGE_KEY_HEX_LEN",
    "AesGcmDecryptionError",
    "EncryptedBundle",
    "decrypt_bundle",
    "encrypt_bundle",
]
