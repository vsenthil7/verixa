"""pytest suite for verixa_runtime.replay.sealer (CP-12.2).

Covers encrypt_bundle / decrypt_bundle round-trip, tamper detection,
storage-key determinism over the ciphertext triple, and the
defence-in-depth tenant_id/audit_id-mismatch path.
"""

from __future__ import annotations

import json
import uuid

import pytest
from verixa_runtime.crypto.aes_gcm import (
    AesGcmCiphertext,
    AesGcmDecryptionError,
    generate_key,
)
from verixa_runtime.replay import (
    STORAGE_KEY_HEX_LEN,
    EncryptedBundle,
    ReplayBundle,
    decrypt_bundle,
    encrypt_bundle,
)

_AUDIT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_TENANT_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
_OTHER_TENANT = uuid.UUID("99999999-9999-9999-9999-999999999999")


def _bundle(**overrides: object) -> ReplayBundle:
    defaults: dict[str, object] = {
        "audit_id": _AUDIT_ID,
        "tenant_id": _TENANT_ID,
        "decision": "allow",
        "risk_score": 0.1,
        "request_envelope": {"k": "v"},
        "timestamp_unix_ns": 1_700_000_000_000_000_000,
    }
    defaults.update(overrides)
    return ReplayBundle(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# EncryptedBundle invariants
# ---------------------------------------------------------------------------


def test_encrypted_bundle_rejects_wrong_storage_key_length() -> None:
    nonce = b"\x00" * 12
    ct = AesGcmCiphertext(
        nonce=nonce, ciphertext=b"\x00" * 32, associated_data=b"x"
    )
    with pytest.raises(ValueError, match="storage_key"):
        EncryptedBundle(
            ciphertext=ct,
            storage_key="a" * 63,
            tenant_id=_TENANT_ID,
            audit_id=_AUDIT_ID,
        )


def test_encrypted_bundle_rejects_non_hex_storage_key() -> None:
    nonce = b"\x00" * 12
    ct = AesGcmCiphertext(
        nonce=nonce, ciphertext=b"\x00" * 32, associated_data=b"x"
    )
    with pytest.raises(ValueError, match="lowercase hex"):
        EncryptedBundle(
            ciphertext=ct,
            storage_key="G" * 64,
            tenant_id=_TENANT_ID,
            audit_id=_AUDIT_ID,
        )


# ---------------------------------------------------------------------------
# encrypt_bundle / decrypt_bundle round-trip
# ---------------------------------------------------------------------------


def test_round_trip_minimal_bundle() -> None:
    key = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key)
    # Storage key is 64 hex chars.
    assert len(encrypted.storage_key) == STORAGE_KEY_HEX_LEN
    assert encrypted.tenant_id == _TENANT_ID
    assert encrypted.audit_id == _AUDIT_ID
    # Decrypt yields the original bundle.
    recovered = decrypt_bundle(encrypted, key)
    assert recovered.audit_id == b.audit_id
    assert recovered.tenant_id == b.tenant_id
    assert recovered.decision == b.decision
    assert recovered.risk_score == pytest.approx(b.risk_score)


def test_round_trip_preserves_request_envelope() -> None:
    key = generate_key()
    b = _bundle(
        request_envelope={
            "nested": {"a": 1, "b": [1, 2, 3]},
            "unicode": "café",
        }
    )
    encrypted = encrypt_bundle(b, key)
    recovered = decrypt_bundle(encrypted, key)
    assert recovered.request_envelope == b.request_envelope


def test_wrong_key_fails_decryption() -> None:
    key_a = generate_key()
    key_b = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key_a)
    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(encrypted, key_b)


def test_tampered_ciphertext_fails_decryption() -> None:
    key = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key)
    # Flip a byte in the ciphertext.
    tampered_ct = AesGcmCiphertext(
        nonce=encrypted.ciphertext.nonce,
        ciphertext=bytes([encrypted.ciphertext.ciphertext[0] ^ 0xFF])
        + encrypted.ciphertext.ciphertext[1:],
        associated_data=encrypted.ciphertext.associated_data,
    )
    tampered_encrypted = EncryptedBundle(
        ciphertext=tampered_ct,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=encrypted.audit_id,
    )
    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(tampered_encrypted, key)


def test_tampered_associated_data_fails_decryption() -> None:
    """Swap the AD for a forged version targeting a different tenant;
    auth tag must fail."""
    key = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key)
    bad_ad = json.dumps(
        {
            "tenant_id": str(_OTHER_TENANT),
            "audit_id": str(_AUDIT_ID),
            "schema_version": 1,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    tampered_ct = AesGcmCiphertext(
        nonce=encrypted.ciphertext.nonce,
        ciphertext=encrypted.ciphertext.ciphertext,
        associated_data=bad_ad,
    )
    tampered_encrypted = EncryptedBundle(
        ciphertext=tampered_ct,
        storage_key=encrypted.storage_key,
        tenant_id=_OTHER_TENANT,
        audit_id=_AUDIT_ID,
    )
    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(tampered_encrypted, key)


# ---------------------------------------------------------------------------
# Storage-key determinism + uniqueness
# ---------------------------------------------------------------------------


def test_storage_key_deterministic_for_same_ciphertext() -> None:
    """Two EncryptedBundles built from the same AesGcmCiphertext yield
    the same storage key. (We can't get this from two encrypt_bundle
    calls because each generates a fresh nonce.)"""
    key = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key)
    # Re-derive storage key from the ciphertext bytes alone.
    from verixa_runtime.replay.sealer import _content_address
    redrived = _content_address(encrypted.ciphertext)
    assert redrived == encrypted.storage_key


def test_distinct_nonces_yield_distinct_storage_keys() -> None:
    """Two encrypt_bundle calls on identical input produce different
    storage_keys because AES-GCM uses a fresh random nonce each time."""
    key = generate_key()
    b = _bundle()
    a = encrypt_bundle(b, key)
    c = encrypt_bundle(b, key)
    assert a.storage_key != c.storage_key
    # Both still decrypt to the same plaintext.
    assert decrypt_bundle(a, key).audit_id == decrypt_bundle(c, key).audit_id


# ---------------------------------------------------------------------------
# Defence-in-depth: bundle tenant/audit id must match EncryptedBundle label
# ---------------------------------------------------------------------------


def test_decrypted_bundle_tenant_id_mismatch_rejected() -> None:
    """Construct an EncryptedBundle that claims a different tenant_id
    than the plaintext inside; decrypt must raise ValueError on the
    cross-check even though the ciphertext authenticates."""
    key = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key)
    # Forge the label without touching the ciphertext.
    forged = EncryptedBundle(
        ciphertext=encrypted.ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=_OTHER_TENANT,  # lie about which tenant this is for
        audit_id=encrypted.audit_id,
    )
    with pytest.raises(ValueError, match="tenant_id"):
        decrypt_bundle(forged, key)


def test_decrypted_bundle_audit_id_mismatch_rejected() -> None:
    key = generate_key()
    b = _bundle()
    encrypted = encrypt_bundle(b, key)
    forged = EncryptedBundle(
        ciphertext=encrypted.ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=uuid.uuid4(),  # different audit_id label
    )
    with pytest.raises(ValueError, match="audit_id"):
        decrypt_bundle(forged, key)
