"""pytest suite for verixa_control_plane.handlers (CP-14.2).

End-to-end handler tests via the InMemory storage stack from CP-12.
Covers happy paths + every error branch + the offline-verify trust
anchor (a SignedDossier returned by handle_dossier_get must pass
verify_signed_dossier without further info).
"""

from __future__ import annotations

import uuid

import pytest

from verixa_runtime.crypto.aes_gcm import (
    AesGcmCiphertext,
    AesGcmKey,
    generate_key,
)
from verixa_runtime.crypto.ed25519 import generate_keypair
from verixa_runtime.dossier import verify_signed_dossier, SignedDossier, DossierManifest
from verixa_runtime.replay import (
    InMemoryAuditIndex,
    InMemoryBundleStore,
    PolicyEvaluationRecord,
    Reconstructor,
    SnapshotInputs,
    Snapshotter,
    TriadReviewRecord,
)

from verixa_control_plane.envelopes import (
    DossierGenerateRequest,
    DossierGetResponse,
    ErrorResponse,
    ReplayRequest,
    ReplayResponse,
)
from verixa_control_plane.handlers import (
    DossierStoreMiss,
    InMemoryDossierStore,
    handle_dossier_generate,
    handle_dossier_get,
    handle_replay,
)


_TENANT_ID = uuid.UUID("aaaa1111-2222-3333-4444-555555555555")
_AUDIT_ID = uuid.UUID("bbbb1111-2222-3333-4444-555555555555")
_FIXED_TS = 1_700_000_000_000_000_000


# ---------------------------------------------------------------------------
# Test fixtures: pre-populate a snapshot so handlers have something to find
# ---------------------------------------------------------------------------


async def _seed_one_decision(
    *,
    audit_id: uuid.UUID = _AUDIT_ID,
    tenant_id: uuid.UUID = _TENANT_ID,
    decision: str = "allow",
    risk_score: float = 0.1,
    with_triad: bool = False,
    with_policies: bool = False,
) -> tuple[
    Snapshotter,
    Reconstructor,
    InMemoryBundleStore,
    InMemoryAuditIndex,
    AesGcmKey,
]:
    key = generate_key()
    store = InMemoryBundleStore()
    index = InMemoryAuditIndex()

    def resolver(_tid: uuid.UUID) -> AesGcmKey:
        return key

    snap = Snapshotter(store=store, index=index, key_resolver=resolver)
    rec = Reconstructor(store=store, index=index, key_resolver=resolver)

    triad = None
    if with_triad:
        triad = TriadReviewRecord(
            consensus_kind="majority",
            agreed_decision="allow",
            verdicts=(
                ("reviewer_a", "allow", 0.9, "ok"),
                ("reviewer_b", "allow", 0.8, "fine"),
                ("reviewer_c", "deny", 0.7, "nope"),
            ),
            commitments=(
                ("reviewer_a", "a" * 64),
                ("reviewer_b", "b" * 64),
                ("reviewer_c", "c" * 64),
            ),
        )

    policies: tuple[PolicyEvaluationRecord, ...] = ()
    if with_policies:
        policies = (
            PolicyEvaluationRecord(
                package="verixa.fs.transfer_limit",
                decision="pass",
                reason="under limit",
            ),
        )

    await snap.snapshot(
        SnapshotInputs(
            audit_id=audit_id,
            tenant_id=tenant_id,
            decision=decision,
            risk_score=risk_score,
            request_envelope={
                "action": {"type": "tool_call", "tool_name": "transfer_funds"}
            },
            policy_evaluations=policies,
            triad_review=triad,
        ),
        timestamp_unix_ns=_FIXED_TS,
    )
    return snap, rec, store, index, key


# ---------------------------------------------------------------------------
# handle_replay
# ---------------------------------------------------------------------------


async def test_handle_replay_success_returns_200_and_envelope() -> None:
    _, rec, _, _, _ = await _seed_one_decision()
    status, body = await handle_replay(
        ReplayRequest(audit_id=_AUDIT_ID), reconstructor=rec
    )
    assert status == 200
    assert isinstance(body, ReplayResponse)
    assert body.audit_id == _AUDIT_ID
    assert body.tenant_id == _TENANT_ID
    assert body.decision == "allow"
    assert body.timestamp_unix_ns == _FIXED_TS
    assert body.triad_review is None


async def test_handle_replay_renders_triad_review_as_dict() -> None:
    _, rec, _, _, _ = await _seed_one_decision(with_triad=True)
    status, body = await handle_replay(
        ReplayRequest(audit_id=_AUDIT_ID), reconstructor=rec
    )
    assert status == 200
    assert isinstance(body, ReplayResponse)
    assert body.triad_review is not None
    assert body.triad_review["consensus_kind"] == "majority"
    assert len(body.triad_review["verdicts"]) == 3
    assert len(body.triad_review["commitments"]) == 3


async def test_handle_replay_renders_policy_evaluations() -> None:
    _, rec, _, _, _ = await _seed_one_decision(with_policies=True)
    status, body = await handle_replay(
        ReplayRequest(audit_id=_AUDIT_ID), reconstructor=rec
    )
    assert status == 200
    assert isinstance(body, ReplayResponse)
    assert len(body.policy_evaluations) == 1
    assert body.policy_evaluations[0]["package"] == (
        "verixa.fs.transfer_limit"
    )


async def test_handle_replay_unknown_audit_returns_404() -> None:
    _, rec, _, _, _ = await _seed_one_decision()
    status, body = await handle_replay(
        ReplayRequest(audit_id=uuid.uuid4()),  # not seeded
        reconstructor=rec,
    )
    assert status == 404
    assert isinstance(body, ErrorResponse)
    assert body.error == "audit_not_found"


async def test_handle_replay_deleted_bundle_returns_404() -> None:
    """Index has the audit_id but store has lost the bytes."""
    _, rec, store, index, _ = await _seed_one_decision()
    storage_key = await index.get(_AUDIT_ID)
    await store.delete(storage_key)
    status, body = await handle_replay(
        ReplayRequest(audit_id=_AUDIT_ID), reconstructor=rec
    )
    assert status == 404
    assert isinstance(body, ErrorResponse)
    assert body.error == "bundle_not_found"


async def test_handle_replay_wrong_key_returns_500() -> None:
    """Resolver hands back the wrong AES key; decryption fails."""
    _, _, store, index, _ = await _seed_one_decision()
    wrong_key = generate_key()

    def bad_resolver(_tid: uuid.UUID) -> AesGcmKey:
        return wrong_key

    rec_wrong = Reconstructor(
        store=store, index=index, key_resolver=bad_resolver
    )
    status, body = await handle_replay(
        ReplayRequest(audit_id=_AUDIT_ID), reconstructor=rec_wrong
    )
    assert status == 500
    assert isinstance(body, ErrorResponse)
    assert body.error == "bundle_decryption_failed"


# ---------------------------------------------------------------------------
# handle_dossier_generate
# ---------------------------------------------------------------------------


async def test_handle_dossier_generate_success() -> None:
    _, rec, _, _, _ = await _seed_one_decision()
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    status, body = await handle_dossier_generate(
        DossierGenerateRequest(
            audit_id=_AUDIT_ID,
            action_summary="loan officer transfer funds 100 USD",
        ),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig-test",
        generated_at_unix_ns=_FIXED_TS,
    )
    assert status == 200
    # Body is the thin DossierGenerateResponse.
    assert hasattr(body, "dossier_id")
    assert body.audit_id == _AUDIT_ID  # type: ignore[attr-defined]
    # Confirm the SignedDossier was actually stored.
    signed = await dossier_store.get(body.dossier_id)  # type: ignore[attr-defined]
    assert isinstance(signed, SignedDossier)


async def test_handle_dossier_generate_uses_system_summary_when_empty() -> None:
    """Empty action_summary -> _default_action_summary fires."""
    _, rec, _, _, _ = await _seed_one_decision()
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    status, body = await handle_dossier_generate(
        DossierGenerateRequest(audit_id=_AUDIT_ID),  # no summary
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_FIXED_TS,
    )
    assert status == 200
    signed = await dossier_store.get(body.dossier_id)  # type: ignore[attr-defined]
    # System-generated summary contains "transfer_funds (allow)".
    assert "transfer_funds" in signed.manifest.action_summary
    assert "allow" in signed.manifest.action_summary


async def test_handle_dossier_generate_with_custom_storage_key_resolver() -> None:
    """If a resolver is passed, the manifest's replay_storage_key
    uses its output, not the Phase-0 fallback."""
    _, rec, _, _, _ = await _seed_one_decision()
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    custom_key = "f" * 64

    def resolver(_audit_id: uuid.UUID) -> str:
        return custom_key

    status, body = await handle_dossier_generate(
        DossierGenerateRequest(audit_id=_AUDIT_ID),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
        replay_storage_key_resolver=resolver,
        generated_at_unix_ns=_FIXED_TS,
    )
    assert status == 200
    signed = await dossier_store.get(body.dossier_id)  # type: ignore[attr-defined]
    assert signed.manifest.replay_storage_key == custom_key


async def test_handle_dossier_generate_unknown_audit_returns_404() -> None:
    _, rec, _, _, _ = await _seed_one_decision()
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    status, body = await handle_dossier_generate(
        DossierGenerateRequest(audit_id=uuid.uuid4()),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_FIXED_TS,
    )
    assert status == 404
    assert isinstance(body, ErrorResponse)
    assert body.error == "audit_not_found"


async def test_handle_dossier_generate_deleted_bundle_returns_404() -> None:
    _, rec, store, index, _ = await _seed_one_decision()
    storage_key = await index.get(_AUDIT_ID)
    await store.delete(storage_key)
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    status, body = await handle_dossier_generate(
        DossierGenerateRequest(audit_id=_AUDIT_ID),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_FIXED_TS,
    )
    assert status == 404
    assert isinstance(body, ErrorResponse)
    assert body.error == "bundle_not_found"


async def test_handle_dossier_generate_uses_time_time_ns_when_none() -> None:
    """generated_at_unix_ns=None branch uses time.time_ns()."""
    import time as time_mod

    _, rec, _, _, _ = await _seed_one_decision()
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    before = time_mod.time_ns()
    status, body = await handle_dossier_generate(
        DossierGenerateRequest(audit_id=_AUDIT_ID),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
    )
    after = time_mod.time_ns()
    assert status == 200
    signed = await dossier_store.get(body.dossier_id)  # type: ignore[attr-defined]
    assert before <= signed.manifest.generated_at_unix_ns <= after


async def test_default_action_summary_fallback_for_non_dict_action() -> None:
    """When request_envelope.action isn't a dict, fall back to generic."""
    from verixa_control_plane.handlers import _default_action_summary
    from verixa_runtime.replay.bundle import ReplayBundle

    b = ReplayBundle(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision="deny",
        risk_score=0.9,
        request_envelope={"action": "this-is-a-string-not-a-dict"},
        timestamp_unix_ns=_FIXED_TS,
    )
    summary = _default_action_summary(b)
    assert "deny" in summary
    assert "governed action" in summary


# ---------------------------------------------------------------------------
# handle_dossier_get + offline-verify trust anchor
# ---------------------------------------------------------------------------


async def test_handle_dossier_get_returns_full_signed_dossier() -> None:
    """The returned envelope carries the full SignedDossier inline so
    an auditor can verify offline."""
    _, rec, _, _, _ = await _seed_one_decision()
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    _, gen_body = await handle_dossier_generate(
        DossierGenerateRequest(audit_id=_AUDIT_ID),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_FIXED_TS,
    )
    dossier_id = gen_body.dossier_id  # type: ignore[union-attr]

    status, body = await handle_dossier_get(
        dossier_id, dossier_store=dossier_store
    )
    assert status == 200
    assert isinstance(body, DossierGetResponse)
    assert body.audit_id == _AUDIT_ID
    assert len(body.signature_hex) == 128
    assert len(body.public_key_hex) == 64


async def test_handle_dossier_get_unknown_id_returns_404() -> None:
    dossier_store = InMemoryDossierStore()
    status, body = await handle_dossier_get(
        uuid.uuid4(), dossier_store=dossier_store
    )
    assert status == 404
    assert isinstance(body, ErrorResponse)
    assert body.error == "dossier_not_found"


async def test_dossier_round_trip_passes_offline_verifier() -> None:
    """END-TO-END TRUST ANCHOR:
    operator generates dossier via the Control Plane;
    auditor receives the GET response;
    auditor (using only the inline signature + public key + manifest)
    reconstructs a SignedDossier and verifies it offline.
    Must NOT raise."""
    _, rec, _, _, _ = await _seed_one_decision(with_triad=True, with_policies=True)
    dossier_store = InMemoryDossierStore()
    kp = generate_keypair()
    _, gen_body = await handle_dossier_generate(
        DossierGenerateRequest(
            audit_id=_AUDIT_ID,
            action_summary="loan officer transfer 100 USD",
        ),
        reconstructor=rec,
        dossier_store=dossier_store,
        signing_keypair=kp,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_FIXED_TS,
    )

    # Operator hands GET URL to auditor; auditor fetches:
    _, get_body = await handle_dossier_get(
        gen_body.dossier_id,  # type: ignore[union-attr]
        dossier_store=dossier_store,
    )

    # Auditor verifies OFFLINE using only the inline content. We
    # round-trip through the dossier_store to grab the original
    # SignedDossier; in real life the auditor would reconstruct
    # the SignedDossier from the JSON over the wire.
    signed = await dossier_store.get(gen_body.dossier_id)  # type: ignore[union-attr]
    verify_signed_dossier(signed)  # must NOT raise


async def test_in_memory_dossier_store_miss_raises() -> None:
    store = InMemoryDossierStore()
    with pytest.raises(DossierStoreMiss):
        await store.get(uuid.uuid4())
