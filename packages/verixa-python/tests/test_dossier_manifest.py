"""pytest suite for verixa_runtime.dossier.manifest (CP-13.1 / 13.2).

Covers dataclass validation, build_manifest projection, canonical
serialisation determinism, sign + verify round-trip, and every
verify failure branch.
"""

from __future__ import annotations

import json
import uuid

import pytest
from verixa_runtime.crypto.ed25519 import generate_keypair
from verixa_runtime.dossier import (
    DossierManifest,
    DossierManifestError,
    SignedDossier,
    build_manifest,
    canonicalise_manifest,
    sign_manifest,
    verify_signed_dossier,
)
from verixa_runtime.replay import (
    PolicyEvaluationRecord,
    ReplayBundle,
    TriadReviewRecord,
)

_AUDIT_ID = uuid.UUID("aaaa1111-2222-3333-4444-555555555555")
_TENANT_ID = uuid.UUID("bbbb1111-2222-3333-4444-555555555555")
_NOW_NS = 1_700_000_000_000_000_000


def _bundle(
    *,
    decision: str = "allow",
    risk_score: float = 0.1,
    policy_evaluations: tuple[PolicyEvaluationRecord, ...] = (),
    triad: TriadReviewRecord | None = None,
    retrieved: tuple[tuple[str, str], ...] = (),
) -> ReplayBundle:
    return ReplayBundle(
        audit_id=_AUDIT_ID,
        tenant_id=_TENANT_ID,
        decision=decision,
        risk_score=risk_score,
        request_envelope={"x": 1},
        retrieved_documents=retrieved,
        policy_evaluations=policy_evaluations,
        triad_review=triad,
        timestamp_unix_ns=_NOW_NS,
    )


# ---------------------------------------------------------------------------
# DossierManifest invariants
# ---------------------------------------------------------------------------


def _minimal_manifest(**overrides) -> DossierManifest:  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "audit_id": _AUDIT_ID,
        "tenant_id": _TENANT_ID,
        "generated_at_unix_ns": _NOW_NS,
        "decision": "allow",
        "risk_score": 0.1,
        "risk_classification": "low",
        "action_summary": "tool_call read_account_balance",
        "replay_storage_key": "0" * 64,
        "signing_key_id": "verixa-sig-test",
    }
    defaults.update(overrides)
    return DossierManifest(**defaults)  # type: ignore[arg-type]


def test_manifest_rejects_unknown_decision() -> None:
    with pytest.raises(DossierManifestError, match="decision"):
        _minimal_manifest(decision="maybe")


def test_manifest_rejects_risk_below_zero() -> None:
    with pytest.raises(DossierManifestError, match="risk_score"):
        _minimal_manifest(risk_score=-0.01)


def test_manifest_rejects_risk_above_one() -> None:
    with pytest.raises(DossierManifestError, match="risk_score"):
        _minimal_manifest(risk_score=1.01)


def test_manifest_rejects_unknown_classification() -> None:
    with pytest.raises(DossierManifestError, match="risk_classification"):
        _minimal_manifest(risk_classification="absurd")


def test_manifest_rejects_negative_generated_at() -> None:
    with pytest.raises(DossierManifestError, match="generated_at_unix_ns"):
        _minimal_manifest(generated_at_unix_ns=-1)


def test_manifest_rejects_unknown_schema_version() -> None:
    with pytest.raises(DossierManifestError, match="schema_version"):
        _minimal_manifest(schema_version=99)


def test_signed_dossier_rejects_wrong_signature_length() -> None:
    m = _minimal_manifest()
    with pytest.raises(DossierManifestError, match="signature_hex"):
        SignedDossier(
            manifest=m,
            signature_hex="a" * 127,  # one short
            public_key_hex="b" * 64,
        )


def test_signed_dossier_rejects_wrong_public_key_length() -> None:
    m = _minimal_manifest()
    with pytest.raises(DossierManifestError, match="public_key_hex"):
        SignedDossier(
            manifest=m,
            signature_hex="a" * 128,
            public_key_hex="b" * 63,
        )


# ---------------------------------------------------------------------------
# build_manifest -- ReplayBundle projection
# ---------------------------------------------------------------------------


def test_build_manifest_low_risk_classification() -> None:
    b = _bundle(risk_score=0.05)
    m = build_manifest(
        bundle=b,
        replay_storage_key="0" * 64,
        signing_key_id="verixa-sig-low",
        generated_at_unix_ns=_NOW_NS,
        action_summary="tool_call read_x",
    )
    assert m.risk_classification == "low"


def test_build_manifest_medium_high_critical_classification() -> None:
    """Cover the three non-low buckets in one test."""
    for score, expected in [(0.25, "medium"), (0.55, "high"), (0.95, "critical")]:
        m = build_manifest(
            bundle=_bundle(risk_score=score),
            replay_storage_key="0" * 64,
            signing_key_id="verixa-sig-x",
            generated_at_unix_ns=_NOW_NS,
            action_summary="x",
        )
        assert m.risk_classification == expected, (score, expected)


def test_build_manifest_includes_policy_evaluations() -> None:
    b = _bundle(
        policy_evaluations=(
            PolicyEvaluationRecord(
                package="verixa.fs.transfer_limit",
                decision="fail",
                reason="over limit",
            ),
            PolicyEvaluationRecord(
                package="verixa.core.workflow",
                decision="pass",
                reason="ok",
            ),
        )
    )
    m = build_manifest(
        bundle=b,
        replay_storage_key="0" * 64,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_NOW_NS,
        action_summary="x",
    )
    assert len(m.policy_evaluations) == 2
    assert m.policy_evaluations[0] == (
        "verixa.fs.transfer_limit", "fail", "over limit"
    )


def test_build_manifest_includes_triad_review_with_dissenters() -> None:
    """MAJORITY consensus -> dissenters computed from verdicts whose
    decision differs from the agreed_decision."""
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
    m = build_manifest(
        bundle=_bundle(triad=triad),
        replay_storage_key="0" * 64,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_NOW_NS,
        action_summary="x",
    )
    assert m.triad_consensus == "majority"
    assert m.triad_agreed_decision == "allow"
    assert m.triad_dissenters == ("reviewer_c",)


def test_build_manifest_triad_split_has_no_dissenters_field() -> None:
    """SPLIT consensus -> agreed_decision is None -> dissenters is
    empty (we can't say who dissented from nobody)."""
    triad = TriadReviewRecord(
        consensus_kind="split",
        agreed_decision=None,
        verdicts=(
            ("reviewer_a", "allow", 0.9, "ok"),
            ("reviewer_b", "deny", 0.8, "no"),
            ("reviewer_c", "escalate", 0.7, "maybe"),
        ),
    )
    m = build_manifest(
        bundle=_bundle(triad=triad),
        replay_storage_key="0" * 64,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_NOW_NS,
        action_summary="x",
    )
    assert m.triad_consensus == "split"
    assert m.triad_agreed_decision is None
    assert m.triad_dissenters == ()


def test_build_manifest_no_triad_review_leaves_fields_none() -> None:
    m = build_manifest(
        bundle=_bundle(),  # triad=None
        replay_storage_key="0" * 64,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_NOW_NS,
        action_summary="x",
    )
    assert m.triad_consensus is None
    assert m.triad_agreed_decision is None
    assert m.triad_dissenters == ()


def test_build_manifest_includes_retrieved_documents() -> None:
    b = _bundle(
        retrieved=(
            ("doc_001", "f" * 64),
            ("doc_002", "0" * 64),
        )
    )
    m = build_manifest(
        bundle=b,
        replay_storage_key="0" * 64,
        signing_key_id="verixa-sig",
        generated_at_unix_ns=_NOW_NS,
        action_summary="x",
    )
    assert m.retrieved_documents == (
        ("doc_001", "f" * 64),
        ("doc_002", "0" * 64),
    )


# ---------------------------------------------------------------------------
# canonicalise_manifest determinism
# ---------------------------------------------------------------------------


def test_canonicalise_is_deterministic() -> None:
    m = _minimal_manifest()
    assert canonicalise_manifest(m) == canonicalise_manifest(m)


def test_canonicalise_keys_are_sorted() -> None:
    m = _minimal_manifest()
    parsed = json.loads(canonicalise_manifest(m))
    assert list(parsed.keys()) == sorted(parsed.keys())


# ---------------------------------------------------------------------------
# sign + verify round-trip
# ---------------------------------------------------------------------------


def test_sign_verify_round_trip() -> None:
    kp = generate_keypair()
    m = _minimal_manifest()
    signed = sign_manifest(
        m, private_key=kp.private_key, public_key=kp.public_key
    )
    assert len(signed.signature_hex) == 128
    assert len(signed.public_key_hex) == 64
    # Round-trip via verify: must NOT raise.
    verify_signed_dossier(signed)


def test_verify_rejects_tampered_manifest() -> None:
    """Sign one manifest; reconstruct a SignedDossier with a different
    manifest under the same signature; verification must fail."""
    kp = generate_keypair()
    m_original = _minimal_manifest()
    signed = sign_manifest(
        m_original, private_key=kp.private_key, public_key=kp.public_key
    )
    # Build a different manifest with the same signature.
    m_tampered = _minimal_manifest(decision="deny")  # different decision
    forged = SignedDossier(
        manifest=m_tampered,
        signature_hex=signed.signature_hex,
        public_key_hex=signed.public_key_hex,
    )
    with pytest.raises(DossierManifestError, match="signature"):
        verify_signed_dossier(forged)


def test_verify_rejects_wrong_public_key() -> None:
    """Sign with key A, claim public key B; verification must fail."""
    kp_a = generate_keypair()
    kp_b = generate_keypair()
    m = _minimal_manifest()
    signed_with_a = sign_manifest(
        m, private_key=kp_a.private_key, public_key=kp_a.public_key
    )
    # Replace the public key with B's.
    forged = SignedDossier(
        manifest=signed_with_a.manifest,
        signature_hex=signed_with_a.signature_hex,
        public_key_hex=kp_b.public_key.hex(),
    )
    with pytest.raises(DossierManifestError, match="signature"):
        verify_signed_dossier(forged)


def test_verify_rejects_non_hex_signature() -> None:
    """SignedDossier validation passes 128-char check but the chars
    aren't valid hex; bytes.fromhex fails inside verify."""
    kp = generate_keypair()
    m = _minimal_manifest()
    signed = sign_manifest(
        m, private_key=kp.private_key, public_key=kp.public_key
    )
    # Replace one char with a non-hex character (length still 128).
    bad_sig = "z" + signed.signature_hex[1:]
    forged = SignedDossier(
        manifest=signed.manifest,
        signature_hex=bad_sig,
        public_key_hex=signed.public_key_hex,
    )
    with pytest.raises(DossierManifestError, match="not valid hex"):
        verify_signed_dossier(forged)
