"""CP-37 negative test 7/10: tenant-key compromise + cryptographic-erasure scenarios.

Anchored to BR-05 (cryptographic erasure for GDPR Article 17), BR-06
(per-tenant isolation), NEGATIVE_TEST_PLAN gap 10 (tenant-key compromise
scenarios documented but not yet tested).

Phase 0 cryptographic-erasure architecture (per ADR-0001):

  - Each tenant has a per-tenant AES-256-GCM Data Encryption Key (DEK)
  - DEK lives in-process in Phase 0 (TenantKeyResolver dict); Vault /
    KMS-backed in Phase 1 (ADR-0008)
  - Replay bundles encrypted with the tenant's DEK
  - Destroying the DEK renders the bundles cryptographically
    unreadable, even though the ciphertext bytes remain on disk
  - Audit ledger entries remain intact (signed, hash-chained, NOT
    encrypted) because regulatory retention typically prevails

Attack model 1 - DEK destruction (GDPR erasure):
  Customer's DPO submits Article 17 erasure - Verixa destroys the
  tenant's DEK - bundles unreadable forever - audit-index entries
  remain. Tests prove this is exactly what happens.

Attack model 2 - Single tenant's DEK leaks:
  Attacker obtains Tenant A's DEK. Blast radius MUST be exactly
  Tenant A's data - they cannot decrypt Tenant B's bundles even with
  Tenant A's full DEK. Tests prove per-tenant isolation holds.

Attack model 3 - Ciphertext modification (AEAD detection):
  Attacker tries to mutate bytes in the ciphertext. AES-GCM auth-tag
  detects any modification; decrypt raises AesGcmDecryptionError.

Attack model 4 - Wrong nonce / cross-bundle nonce:
  Attacker has DEK + ciphertext but the nonce in the EncryptedBundle
  is wrong. AEAD authentication fails.

Attack model 5 - Catastrophic key loss:
  All tenant DEKs lost simultaneously (DR Plan section 4.2.3).
  Every bundle unreadable; audit-index preserved.
"""

from __future__ import annotations

import uuid

import pytest
from verixa_runtime.crypto.aes_gcm import (
    AesGcmCiphertext,
    AesGcmDecryptionError,
    AesGcmKey,
    generate_key,
)
from verixa_runtime.replay import (
    AuditIndexMiss,
    EncryptedBundle,
    InMemoryAuditIndex,
    InMemoryBundleStore,
    Reconstructor,
    Snapshotter,
    decrypt_bundle,
)
from verixa_runtime.replay.snapshotter import ReconstructorAuditIdMismatch, SnapshotInputs

_TENANT_A = uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa")
_TENANT_B = uuid.UUID("bbbbbbbb-2222-2222-2222-bbbbbbbbbbbb")


@pytest.fixture
def two_tenant_replay_system() -> tuple[
    InMemoryBundleStore,
    InMemoryAuditIndex,
    dict[uuid.UUID, AesGcmKey],
    Snapshotter,
    Reconstructor,
]:
    """Spin up replay infrastructure with 2 tenants having distinct DEKs."""
    bundle_store = InMemoryBundleStore()
    audit_index = InMemoryAuditIndex()
    tenant_keys: dict[uuid.UUID, AesGcmKey] = {
        _TENANT_A: generate_key(),
        _TENANT_B: generate_key(),
    }

    def key_resolver(tid: uuid.UUID) -> AesGcmKey:
        if tid not in tenant_keys:
            raise KeyError(f"tenant {tid} has no DEK")
        return tenant_keys[tid]

    snapshotter = Snapshotter(
        store=bundle_store, index=audit_index, key_resolver=key_resolver
    )
    reconstructor = Reconstructor(
        store=bundle_store, index=audit_index, key_resolver=key_resolver
    )

    return bundle_store, audit_index, tenant_keys, snapshotter, reconstructor


async def _seed_one_for_tenant(
    snapshotter: Snapshotter,
    *,
    tenant_id: uuid.UUID,
    audit_id: uuid.UUID,
    action_tool: str = "transfer_funds",
) -> None:
    """Seed one replay snapshot for a tenant."""
    await snapshotter.snapshot(
        SnapshotInputs(
            audit_id=audit_id,
            tenant_id=tenant_id,
            decision="allow",
            risk_score=0.15,
            request_envelope={
                "action": {
                    "type": "tool_call",
                    "tool_name": action_tool,
                },
                "tenant_marker": str(tenant_id),
            },
        )
    )


# ---------------------------------------------------------------------------
# Attack model 1 - DEK destruction (GDPR Article 17 erasure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dek_destruction_makes_bundle_unreadable(
    two_tenant_replay_system,
) -> None:
    """Article 17 erasure: destroy Tenant A's DEK; Tenant A's bundle MUST
    NOT be decryptable thereafter.

    BR-05 cryptographic-erasure expressed as an attack scenario."""
    _, _, tenant_keys, snapshotter, reconstructor = two_tenant_replay_system
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    # Verify the bundle is readable BEFORE erasure.
    bundle_before = await reconstructor.reconstruct(audit_id)
    assert bundle_before.tenant_id == _TENANT_A

    # ---- ERASE ----
    del tenant_keys[_TENANT_A]

    # After erasure, reconstruct MUST fail. KeyError from the resolver
    # (no DEK to apply); any catch-all decrypt-fallback would be a
    # security bug.
    with pytest.raises(KeyError, match="tenant"):
        await reconstructor.reconstruct(audit_id)


@pytest.mark.asyncio
async def test_dek_destruction_preserves_audit_index_entry(
    two_tenant_replay_system,
) -> None:
    """The audit-index entry MUST remain after DEK destruction.

    Regulatory retention (typically 7 years) prevails over Article 17
    for the audit record; only the subject-content bundle is rendered
    unreadable. The audit-id-to-storage-key pointer remains as evidence
    that the decision occurred.

    This asserts the design intent that erasure is *redaction-with-
    evidence-preservation*, not *full deletion of evidence*."""
    _, audit_index, tenant_keys, snapshotter, _ = two_tenant_replay_system
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    storage_key_before = await audit_index.get(audit_id)
    assert isinstance(storage_key_before, str)
    assert len(storage_key_before) == 64

    # ---- ERASE ----
    del tenant_keys[_TENANT_A]

    # Index pointer STILL there post-erasure (redaction preserves the
    # ledger row).
    storage_key_after = await audit_index.get(audit_id)
    assert storage_key_after == storage_key_before, (
        "Audit ledger pointer must NOT change on cryptographic erasure"
    )


@pytest.mark.asyncio
async def test_dek_regeneration_does_not_decrypt_old_bundle(
    two_tenant_replay_system,
) -> None:
    """After erasure, creating a NEW DEK with the same tenant_id MUST
    NOT decrypt the old bundle.

    DEKs are random; a new generate_key() call returns different bytes;
    AES-GCM auth-tag rejection catches the mismatch. An implementation
    that allowed 'recovery' by re-keying would violate the erasure
    guarantee."""
    _, _, tenant_keys, snapshotter, reconstructor = two_tenant_replay_system
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    # ---- ERASE ----
    del tenant_keys[_TENANT_A]

    # ---- RE-CREATE (attacker scenario: "recover" tenant by re-keying)
    tenant_keys[_TENANT_A] = generate_key()

    # Reconstruction MUST fail - auth-tag mismatch under the new DEK.
    with pytest.raises(AesGcmDecryptionError):
        await reconstructor.reconstruct(audit_id)


# ---------------------------------------------------------------------------
# Attack model 2 - Cross-tenant DEK isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_a_dek_cannot_decrypt_tenant_b_bundle(
    two_tenant_replay_system,
) -> None:
    """The most critical isolation property: an attacker who has full
    knowledge of Tenant A's DEK cannot decrypt Tenant B's bundles.

    Attack scenario: insider exfiltrates Tenant A's DEK; tries to apply
    it to a Tenant B bundle stored in the same shared object store."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id_b = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_B, audit_id=audit_id_b
    )

    # Get Tenant B's encrypted bundle.
    storage_key_b = await audit_index.get(audit_id_b)
    encrypted_b = await bundle_store.get(storage_key_b)

    # Try to decrypt with Tenant A's DEK. MUST fail.
    tenant_a_dek = tenant_keys[_TENANT_A]
    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(encrypted_b, tenant_a_dek)


@pytest.mark.asyncio
async def test_blast_radius_of_compromised_dek_is_one_tenant(
    two_tenant_replay_system,
) -> None:
    """Same test from the blast-radius framing: if Tenant A's DEK is
    fully compromised, every other tenant's data MUST remain protected.

    This is the per-tenant isolation BR-06 guarantee expressed as a
    negative test."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id_a = uuid.uuid4()
    audit_id_b = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id_a
    )
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_B, audit_id=audit_id_b
    )

    # Attacker has A's DEK
    tenant_a_dek = tenant_keys[_TENANT_A]

    # Confirm A can be read with A's DEK
    storage_key_a = await audit_index.get(audit_id_a)
    encrypted_a = await bundle_store.get(storage_key_a)
    bundle_a = decrypt_bundle(encrypted_a, tenant_a_dek)
    assert bundle_a.tenant_id == _TENANT_A

    # Confirm B CANNOT be read with A's DEK
    storage_key_b = await audit_index.get(audit_id_b)
    encrypted_b = await bundle_store.get(storage_key_b)
    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(encrypted_b, tenant_a_dek)


# ---------------------------------------------------------------------------
# Attack model 3 - Ciphertext modification (AEAD detection)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ciphertext_byte_modification_detected(
    two_tenant_replay_system,
) -> None:
    """Flipping a single byte in the sealed ciphertext MUST cause
    decryption to fail. AES-GCM auth-tag covers the entire ciphertext.

    Attack scenario: an attacker with write-access to the object store
    (but not the DEK) tries to modify ciphertext bytes."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    storage_key = await audit_index.get(audit_id)
    encrypted = await bundle_store.get(storage_key)

    # Flip one byte in the middle of the ciphertext.
    ct_bytes = encrypted.ciphertext.ciphertext
    midpoint = len(ct_bytes) // 2
    tampered_ct = (
        ct_bytes[:midpoint]
        + bytes([ct_bytes[midpoint] ^ 0x01])
        + ct_bytes[midpoint + 1 :]
    )

    # Build a tampered EncryptedBundle (skip post-init validation by
    # using dataclass.replace on the inner ciphertext field).
    tampered_ciphertext = AesGcmCiphertext(
        nonce=encrypted.ciphertext.nonce,
        ciphertext=tampered_ct,
        associated_data=encrypted.ciphertext.associated_data,
    )
    tampered_bundle = EncryptedBundle(
        ciphertext=tampered_ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=encrypted.audit_id,
    )

    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(tampered_bundle, tenant_keys[_TENANT_A])


@pytest.mark.asyncio
async def test_truncated_ciphertext_detected(
    two_tenant_replay_system,
) -> None:
    """Truncating the ciphertext destroys the auth tag. MUST fail."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    storage_key = await audit_index.get(audit_id)
    encrypted = await bundle_store.get(storage_key)

    truncated_ct = encrypted.ciphertext.ciphertext[
        : len(encrypted.ciphertext.ciphertext) - 8
    ]
    tampered_ciphertext = AesGcmCiphertext(
        nonce=encrypted.ciphertext.nonce,
        ciphertext=truncated_ct,
        associated_data=encrypted.ciphertext.associated_data,
    )
    tampered_bundle = EncryptedBundle(
        ciphertext=tampered_ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=encrypted.audit_id,
    )

    with pytest.raises((AesGcmDecryptionError, ValueError)):
        decrypt_bundle(tampered_bundle, tenant_keys[_TENANT_A])


@pytest.mark.asyncio
async def test_extended_ciphertext_detected(
    two_tenant_replay_system,
) -> None:
    """Appending bytes shifts the auth tag's expected position. MUST fail."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    storage_key = await audit_index.get(audit_id)
    encrypted = await bundle_store.get(storage_key)

    extended_ct = encrypted.ciphertext.ciphertext + b"attacker-appended"
    tampered_ciphertext = AesGcmCiphertext(
        nonce=encrypted.ciphertext.nonce,
        ciphertext=extended_ct,
        associated_data=encrypted.ciphertext.associated_data,
    )
    tampered_bundle = EncryptedBundle(
        ciphertext=tampered_ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=encrypted.audit_id,
    )

    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(tampered_bundle, tenant_keys[_TENANT_A])


# ---------------------------------------------------------------------------
# Attack model 4 - Wrong nonce / AD tampering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_nonce_detected(two_tenant_replay_system) -> None:
    """Using a wrong-but-valid-length nonce with the right DEK + right
    ciphertext MUST fail auth-tag verification."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    storage_key = await audit_index.get(audit_id)
    encrypted = await bundle_store.get(storage_key)

    wrong_nonce = bytes([0xAA] * len(encrypted.ciphertext.nonce))
    tampered_ciphertext = AesGcmCiphertext(
        nonce=wrong_nonce,
        ciphertext=encrypted.ciphertext.ciphertext,
        associated_data=encrypted.ciphertext.associated_data,
    )
    tampered_bundle = EncryptedBundle(
        ciphertext=tampered_ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=encrypted.audit_id,
    )

    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(tampered_bundle, tenant_keys[_TENANT_A])


@pytest.mark.asyncio
async def test_associated_data_tampering_detected(
    two_tenant_replay_system,
) -> None:
    """AES-GCM AD covers (tenant_id, audit_id, schema_version). Tampering
    the AD bytes MUST fail auth-tag verification. This is the structural
    AEAD property that pins each ciphertext to its (tenant, audit) tuple."""
    bundle_store, audit_index, tenant_keys, snapshotter, _ = (
        two_tenant_replay_system
    )
    audit_id = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id
    )

    storage_key = await audit_index.get(audit_id)
    encrypted = await bundle_store.get(storage_key)

    # Tamper the AD bytes (flip one bit).
    ad = encrypted.ciphertext.associated_data
    tampered_ad = bytes([ad[0] ^ 0x01]) + ad[1:]
    tampered_ciphertext = AesGcmCiphertext(
        nonce=encrypted.ciphertext.nonce,
        ciphertext=encrypted.ciphertext.ciphertext,
        associated_data=tampered_ad,
    )
    tampered_bundle = EncryptedBundle(
        ciphertext=tampered_ciphertext,
        storage_key=encrypted.storage_key,
        tenant_id=encrypted.tenant_id,
        audit_id=encrypted.audit_id,
    )

    with pytest.raises(AesGcmDecryptionError):
        decrypt_bundle(tampered_bundle, tenant_keys[_TENANT_A])


# ---------------------------------------------------------------------------
# Attack model 5 - Catastrophic key loss (DR Plan section 4.2.3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catastrophic_key_loss_all_bundles_unreadable(
    two_tenant_replay_system,
) -> None:
    """ADR-0008 + DR Plan section 4.2.3 catastrophic-key-loss: Vault +
    escrow both lost; every tenant's DEK is gone simultaneously.

    Expected: every reconstruction fails; audit-index remains."""
    _, audit_index, tenant_keys, snapshotter, reconstructor = (
        two_tenant_replay_system
    )
    audit_id_a = uuid.uuid4()
    audit_id_b = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id_a
    )
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_B, audit_id=audit_id_b
    )

    # ---- CATASTROPHIC: erase every DEK ----
    tenant_keys.clear()

    # Both reconstructions fail
    with pytest.raises(KeyError):
        await reconstructor.reconstruct(audit_id_a)
    with pytest.raises(KeyError):
        await reconstructor.reconstruct(audit_id_b)

    # But both audit-index pointers still exist (ledger preserved)
    assert await audit_index.get(audit_id_a)
    assert await audit_index.get(audit_id_b)


# ---------------------------------------------------------------------------
# Attack model 6 - Audit-index probing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_index_miss_raises_typed_error(
    two_tenant_replay_system,
) -> None:
    """Probing audit-index with arbitrary UUIDs raises AuditIndexMiss
    rather than returning silent None - explicit typed signal so
    callers cannot conflate 'no entry' with 'data corrupted'."""
    _, audit_index, _, _, _ = two_tenant_replay_system
    bogus = uuid.uuid4()
    with pytest.raises(AuditIndexMiss):
        await audit_index.get(bogus)


# ---------------------------------------------------------------------------
# Attack model 7 - Substituting cross-tenant bundle via swapped audit-index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_swapping_bundle_storage_keys_detected(
    two_tenant_replay_system,
) -> None:
    """If an attacker tampers the audit-index to point Tenant A's audit_id
    at Tenant B's bundle bytes, the reconstruction MUST fail rather than
    return cross-tenant data.

    CP-40 closes this attack: Reconstructor.reconstruct now checks that
    the fetched EncryptedBundle's audit_id matches the requested audit_id
    and raises ReconstructorAuditIdMismatch if they differ.

    Attack scenario reconstruction:
      1. Seed two bundles: audit_id_a -> Tenant A bundle; audit_id_b ->
         Tenant B bundle.
      2. Tamper InMemoryAuditIndex._items directly (bypassing the
         conflict-detection in put()) so audit_id_a points at Tenant
         B's storage_key.
      3. Attempt reconstruct(audit_id_a). Pre-CP-40 this would have
         returned Tenant B's bundle (cross-tenant data exposure).
         Post-CP-40, the audit_id guard fires:
         ReconstructorAuditIdMismatch raised."""
    bundle_store, audit_index, tenant_keys, snapshotter, reconstructor = (
        two_tenant_replay_system
    )
    audit_id_a = uuid.uuid4()
    audit_id_b = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id_a
    )
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_B, audit_id=audit_id_b
    )

    # Sanity: A and B both reconstruct correctly under normal flow.
    bundle_a = await reconstructor.reconstruct(audit_id_a)
    assert bundle_a.tenant_id == _TENANT_A
    bundle_b = await reconstructor.reconstruct(audit_id_b)
    assert bundle_b.tenant_id == _TENANT_B

    # ATTACK: tamper the audit-index to point audit_id_a at
    # Tenant B's storage_key. The conflict-detection in put() would
    # block this via the public API, so we mutate _items directly to
    # simulate an attacker with index-table write access.
    storage_key_b = audit_index._items[audit_id_b]
    audit_index._items[audit_id_a] = storage_key_b

    # CP-40 guard fires: ReconstructorAuditIdMismatch raised because
    # the fetched bundle has audit_id_b baked in but the caller
    # requested audit_id_a.
    with pytest.raises(ReconstructorAuditIdMismatch, match="audit_id mismatch"):
        await reconstructor.reconstruct(audit_id_a)


@pytest.mark.asyncio
async def test_reconstructor_audit_id_guard_message_includes_both_ids(
    two_tenant_replay_system,
) -> None:
    """The ReconstructorAuditIdMismatch message MUST mention both the
    requested audit_id and the actually-fetched audit_id, so operators
    can investigate the tampering. Defence-in-depth: a generic error
    message would lose forensic value."""
    _, audit_index, _, snapshotter, reconstructor = two_tenant_replay_system
    audit_id_a = uuid.uuid4()
    audit_id_b = uuid.uuid4()
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_A, audit_id=audit_id_a
    )
    await _seed_one_for_tenant(
        snapshotter, tenant_id=_TENANT_B, audit_id=audit_id_b
    )

    # Tamper the audit-index
    storage_key_b = audit_index._items[audit_id_b]
    audit_index._items[audit_id_a] = storage_key_b

    # Capture the exception to inspect the message
    with pytest.raises(ReconstructorAuditIdMismatch) as exc_info:
        await reconstructor.reconstruct(audit_id_a)

    msg = str(exc_info.value)
    assert str(audit_id_a) in msg, (
        "exception message must mention the REQUESTED audit_id"
    )
    assert str(audit_id_b) in msg, (
        "exception message must mention the ACTUAL audit_id (the one "
        "found at the tampered storage_key)"
    )
    assert "tampering" in msg or "substitution" in msg, (
        "exception message must hint at the attack class"
    )
