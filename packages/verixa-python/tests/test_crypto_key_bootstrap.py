"""pytest suite for verixa_runtime.crypto.key_bootstrap.

100% line + branch coverage. Tests verify that the bundle is well-formed
and integrates correctly with the underlying ed25519 + aes_gcm primitives.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from verixa_runtime.crypto.aes_gcm import KEY_BYTES as AES_KEY_BYTES
from verixa_runtime.crypto.aes_gcm import AesGcmKey, decrypt, encrypt
from verixa_runtime.crypto.ed25519 import (
    PUBLIC_KEY_BYTES,
    Ed25519KeyPair,
    sign,
    verify,
)
from verixa_runtime.crypto.key_bootstrap import (
    TenantKeyBundle,
    bootstrap_tenant,
    derive_signing_key_id,
)

# ---------------------------------------------------------------------------
# derive_signing_key_id
# ---------------------------------------------------------------------------


def test_derive_signing_key_id_format() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    pk = b"\x00" * 32
    sid = derive_signing_key_id(tid, pk)
    assert sid.startswith("verixa-sig-")
    assert len(sid) == len("verixa-sig-") + 16
    # Must be lowercase hex after the prefix
    suffix = sid.removeprefix("verixa-sig-")
    int(suffix, 16)  # raises ValueError if not hex


def test_derive_signing_key_id_is_deterministic() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    pk = b"\xab" * 32
    assert derive_signing_key_id(tid, pk) == derive_signing_key_id(tid, pk)


def test_derive_signing_key_id_changes_with_pk() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    a = derive_signing_key_id(tid, b"\x00" * 32)
    b = derive_signing_key_id(tid, b"\x01" * 32)
    assert a != b


def test_derive_signing_key_id_changes_with_tenant() -> None:
    pk = b"\xab" * 32
    a = derive_signing_key_id(
        uuid.UUID("00000000-0000-0000-0000-000000000001"), pk
    )
    b = derive_signing_key_id(
        uuid.UUID("00000000-0000-0000-0000-000000000002"), pk
    )
    assert a != b


def test_derive_signing_key_id_matches_canonical_definition() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    pk = b"\xcd" * 32
    expected = "verixa-sig-" + hashlib.sha256(tid.bytes + pk).hexdigest()[:16]
    assert derive_signing_key_id(tid, pk) == expected


def test_derive_signing_key_id_rejects_non_uuid() -> None:
    with pytest.raises(TypeError, match="tenant_id must be uuid.UUID"):
        derive_signing_key_id("not-a-uuid", b"\x00" * 32)  # type: ignore[arg-type]


def test_derive_signing_key_id_rejects_wrong_pk_length() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValueError, match="public_key must be 32 bytes"):
        derive_signing_key_id(tid, b"\x00" * 16)


# ---------------------------------------------------------------------------
# TenantKeyBundle
# ---------------------------------------------------------------------------


def test_bundle_is_frozen() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    bundle = bootstrap_tenant(tid)
    with pytest.raises((AttributeError, Exception)):
        bundle.tenant_id = uuid.uuid4()  # type: ignore[misc]


def test_bundle_rejects_wrong_signing_key_id_prefix() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    with pytest.raises(ValueError, match="must start with 'verixa-sig-'"):
        TenantKeyBundle(
            tenant_id=tid,
            signing_keypair=Ed25519KeyPair(
                private_key=b"\x00" * 32, public_key=b"\x00" * 32
            ),
            signing_key_id="bad-prefix",
            replay_dek=AesGcmKey(key=b"\x00" * 32),
        )


def test_bundle_rejects_non_uuid_tenant() -> None:
    with pytest.raises(TypeError, match="tenant_id must be uuid.UUID"):
        TenantKeyBundle(
            tenant_id="not-uuid",  # type: ignore[arg-type]
            signing_keypair=Ed25519KeyPair(
                private_key=b"\x00" * 32, public_key=b"\x00" * 32
            ),
            signing_key_id="verixa-sig-abc",
            replay_dek=AesGcmKey(key=b"\x00" * 32),
        )


def test_bundle_public_key_property() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    bundle = bootstrap_tenant(tid)
    assert bundle.public_key == bundle.signing_keypair.public_key
    assert len(bundle.public_key) == PUBLIC_KEY_BYTES


# ---------------------------------------------------------------------------
# bootstrap_tenant
# ---------------------------------------------------------------------------


def test_bootstrap_returns_well_formed_bundle() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    bundle = bootstrap_tenant(tid)
    assert bundle.tenant_id == tid
    assert isinstance(bundle.signing_keypair, Ed25519KeyPair)
    assert isinstance(bundle.replay_dek, AesGcmKey)
    assert len(bundle.replay_dek.key) == AES_KEY_BYTES
    assert bundle.signing_key_id.startswith("verixa-sig-")


def test_bootstrap_signing_id_matches_derive() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    bundle = bootstrap_tenant(tid)
    expected = derive_signing_key_id(tid, bundle.public_key)
    assert bundle.signing_key_id == expected


def test_bootstrap_produces_unique_keys_per_call() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    a = bootstrap_tenant(tid)
    b = bootstrap_tenant(tid)
    assert a.signing_keypair.private_key != b.signing_keypair.private_key
    assert a.signing_keypair.public_key != b.signing_keypair.public_key
    assert a.replay_dek.key != b.replay_dek.key
    assert a.signing_key_id != b.signing_key_id


def test_bootstrap_rejects_non_uuid() -> None:
    with pytest.raises(TypeError, match="tenant_id must be uuid.UUID"):
        bootstrap_tenant("not-uuid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration: bundle is usable end-to-end
# ---------------------------------------------------------------------------


def test_bundle_signing_keypair_signs_and_verifies() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    bundle = bootstrap_tenant(tid)
    msg = b"audit-entry-bytes"
    sig = sign(bundle.signing_keypair.private_key, msg)
    verify(bundle.public_key, msg, sig)  # must not raise


def test_bundle_replay_dek_encrypts_and_decrypts() -> None:
    tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    bundle = bootstrap_tenant(tid)
    plaintext = b"replay-snapshot-payload"
    ct = encrypt(bundle.replay_dek, plaintext, b"audit-id-x")
    assert decrypt(bundle.replay_dek, ct) == plaintext


# ---------------------------------------------------------------------------
# Public-API surface
# ---------------------------------------------------------------------------


def test_package_reexports() -> None:
    from verixa_runtime import crypto

    for name in (
        "TenantKeyBundle",
        "bootstrap_tenant",
        "derive_signing_key_id",
    ):
        assert hasattr(crypto, name), f"crypto package missing {name}"
