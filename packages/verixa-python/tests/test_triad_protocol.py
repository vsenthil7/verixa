"""pytest suite for verixa_runtime.triad.protocol (CP-10.1).

Three layers:

  1. Data-class invariants -- ReviewerVerdict + Commitment validation,
     frozen-instance immutability, ConsensusOutcome shape.
  2. Protocol primitives -- canonicalise_verdict determinism + audit-id
     binding; compute_commitment / verify_reveal happy + tamper paths
     incl. label-swap defence; nonce length enforcement; constant-time
     comparison via hmac.compare_digest is exercised by passing partial
     matches and confirming False (we don't measure timing here).
  3. Consensus computation -- UNANIMOUS / MAJORITY / SPLIT /
     INTEGRITY_FAILURE matrix incl. dissenter ordering and
     missing-reveal handling.

Plus Hypothesis property tests:
  - canonicalise_verdict round-trips through compute_commitment +
    verify_reveal for any verdict.
  - Tampered nonces never verify.
  - Two distinct verdicts under the same nonce produce different
    commitments (collision resistance proxy).

Coverage target: 100% line + branch on
verixa_runtime/triad/__init__.py and
verixa_runtime/triad/protocol.py.
"""

from __future__ import annotations

import dataclasses
import json
import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st
from verixa_runtime.triad import (
    Commitment,
    ConsensusKind,
    ConsensusOutcome,
    ReviewerId,
    ReviewerVerdict,
    VerdictDecision,
    canonicalise_verdict,
    compute_commitment,
    compute_consensus,
    generate_nonce,
    verify_reveal,
)
from verixa_runtime.triad.protocol import NONCE_BYTES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_verdict(
    reviewer_id: ReviewerId = ReviewerId.REVIEWER_A,
    decision: VerdictDecision = VerdictDecision.ALLOW,
    confidence: float = 0.9,
    reasoning: str = "looks fine",
    audit_id: uuid.UUID | None = None,
) -> ReviewerVerdict:
    return ReviewerVerdict(
        reviewer_id=reviewer_id,
        decision=decision,
        confidence=confidence,
        reasoning=reasoning,
        audit_id=audit_id or uuid.UUID("11111111-1111-1111-1111-111111111111"),
    )


def _zero_nonce() -> bytes:
    return b"\x00" * NONCE_BYTES


# ---------------------------------------------------------------------------
# Layer 1 -- data-class invariants
# ---------------------------------------------------------------------------


def test_verdict_confidence_valid_range_accepted() -> None:
    _make_verdict(confidence=0.0)
    _make_verdict(confidence=1.0)
    _make_verdict(confidence=0.5)


def test_verdict_confidence_below_zero_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _make_verdict(confidence=-0.01)


def test_verdict_confidence_above_one_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _make_verdict(confidence=1.01)


def test_verdict_is_frozen() -> None:
    v = _make_verdict()
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.confidence = 0.1  # type: ignore[misc]


def test_commitment_valid_hex_accepted() -> None:
    Commitment(reviewer_id=ReviewerId.REVIEWER_A, sha256_hex="a" * 64)
    Commitment(reviewer_id=ReviewerId.REVIEWER_B, sha256_hex="0123456789abcdef" * 4)


def test_commitment_wrong_length_rejected() -> None:
    with pytest.raises(ValueError, match="sha256_hex"):
        Commitment(reviewer_id=ReviewerId.REVIEWER_A, sha256_hex="a" * 63)


def test_commitment_uppercase_hex_rejected() -> None:
    with pytest.raises(ValueError, match="sha256_hex"):
        Commitment(reviewer_id=ReviewerId.REVIEWER_A, sha256_hex="A" * 64)


def test_commitment_non_hex_chars_rejected() -> None:
    with pytest.raises(ValueError, match="sha256_hex"):
        Commitment(reviewer_id=ReviewerId.REVIEWER_A, sha256_hex="g" * 64)


def test_consensus_outcome_default_fields() -> None:
    out = ConsensusOutcome(kind=ConsensusKind.SPLIT)
    assert out.agreed_decision is None
    assert out.dissenters == ()
    assert out.failed_reviewers == ()


# ---------------------------------------------------------------------------
# Layer 2 -- protocol primitives
# ---------------------------------------------------------------------------


def test_canonicalise_verdict_is_deterministic() -> None:
    v = _make_verdict()
    a = canonicalise_verdict(v)
    b = canonicalise_verdict(v)
    assert a == b


def test_canonicalise_verdict_is_sorted_keys() -> None:
    """The output is JSON; parsing it should round-trip the fields."""
    v = _make_verdict()
    payload = json.loads(canonicalise_verdict(v).decode("utf-8"))
    keys = list(payload.keys())
    assert keys == sorted(keys), "canonical form must use sorted keys"


def test_canonicalise_verdict_changes_with_audit_id() -> None:
    """audit_id is part of the binding; otherwise commitments could be
    replayed on a different governed action."""
    v1 = _make_verdict(audit_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))
    v2 = _make_verdict(audit_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"))
    assert canonicalise_verdict(v1) != canonicalise_verdict(v2)


def test_canonicalise_verdict_changes_with_decision() -> None:
    v1 = _make_verdict(decision=VerdictDecision.ALLOW)
    v2 = _make_verdict(decision=VerdictDecision.DENY)
    assert canonicalise_verdict(v1) != canonicalise_verdict(v2)


def test_generate_nonce_returns_correct_length() -> None:
    n = generate_nonce()
    assert len(n) == NONCE_BYTES
    assert isinstance(n, bytes)


def test_generate_nonce_is_random() -> None:
    """Two calls return different nonces with overwhelming probability.

    Probability of collision on 256 bits is 2^-256; if this ever fails
    in practice the world has bigger problems than this test.
    """
    samples = {generate_nonce() for _ in range(8)}
    assert len(samples) == 8


def test_compute_commitment_happy_path() -> None:
    v = _make_verdict()
    nonce = _zero_nonce()
    c = compute_commitment(v, nonce)
    assert c.reviewer_id == v.reviewer_id
    assert len(c.sha256_hex) == 64


def test_compute_commitment_rejects_wrong_nonce_length() -> None:
    v = _make_verdict()
    with pytest.raises(ValueError, match="nonce"):
        compute_commitment(v, b"\x00" * 16)


def test_verify_reveal_happy_path() -> None:
    v = _make_verdict()
    nonce = _zero_nonce()
    c = compute_commitment(v, nonce)
    assert verify_reveal(c, v, nonce) is True


def test_verify_reveal_tampered_nonce_rejected() -> None:
    v = _make_verdict()
    nonce = _zero_nonce()
    c = compute_commitment(v, nonce)
    bad_nonce = b"\xff" + nonce[1:]
    assert verify_reveal(c, v, bad_nonce) is False


def test_verify_reveal_tampered_verdict_rejected() -> None:
    v = _make_verdict(decision=VerdictDecision.ALLOW)
    nonce = _zero_nonce()
    c = compute_commitment(v, nonce)
    forged = _make_verdict(decision=VerdictDecision.DENY)
    assert verify_reveal(c, forged, nonce) is False


def test_verify_reveal_label_swap_rejected() -> None:
    """Commitment.reviewer_id must equal verdict.reviewer_id; this is
    the first guard in verify_reveal and a defence against an
    orchestrator that hands the wrong reviewer's verdict to a
    commitment.

    Setup: build a real (binding) commitment for REVIEWER_A. Then try
    to verify it against a verdict whose reviewer_id is REVIEWER_B.
    The reviewer_id mismatch must short-circuit to False before the
    hash recompute even runs.
    """
    v_a = _make_verdict(reviewer_id=ReviewerId.REVIEWER_A)
    nonce = _zero_nonce()
    c_a = compute_commitment(v_a, nonce)  # reviewer_id=REVIEWER_A
    # A different verdict whose reviewer_id is REVIEWER_B.
    v_b = _make_verdict(reviewer_id=ReviewerId.REVIEWER_B)
    assert verify_reveal(c_a, v_b, nonce) is False


def test_verify_reveal_wrong_nonce_length_rejected() -> None:
    v = _make_verdict()
    nonce = _zero_nonce()
    c = compute_commitment(v, nonce)
    assert verify_reveal(c, v, b"\x00" * 16) is False


# ---------------------------------------------------------------------------
# Layer 3 -- consensus
# ---------------------------------------------------------------------------


def _three_reveals(
    decisions: tuple[VerdictDecision, VerdictDecision, VerdictDecision],
) -> tuple[
    tuple[Commitment, Commitment, Commitment],
    tuple[
        tuple[ReviewerVerdict, bytes],
        tuple[ReviewerVerdict, bytes],
        tuple[ReviewerVerdict, bytes],
    ],
]:
    """Helper: build commitments + reveals for three given decisions."""
    rids = (ReviewerId.REVIEWER_A, ReviewerId.REVIEWER_B, ReviewerId.REVIEWER_C)
    nonces = (b"\x01" * NONCE_BYTES, b"\x02" * NONCE_BYTES, b"\x03" * NONCE_BYTES)
    verdicts = tuple(
        _make_verdict(reviewer_id=rid, decision=d)
        for rid, d in zip(rids, decisions, strict=False)
    )
    commitments = tuple(
        compute_commitment(v, n) for v, n in zip(verdicts, nonces, strict=False)
    )
    reveals = tuple(zip(verdicts, nonces, strict=False))
    return commitments, reveals  # type: ignore[return-value]


def test_consensus_unanimous_allow() -> None:
    cs, rs = _three_reveals(
        (VerdictDecision.ALLOW, VerdictDecision.ALLOW, VerdictDecision.ALLOW)
    )
    out = compute_consensus(cs, rs)
    assert out.kind == ConsensusKind.UNANIMOUS
    assert out.agreed_decision == VerdictDecision.ALLOW
    assert out.dissenters == ()


def test_consensus_unanimous_deny() -> None:
    cs, rs = _three_reveals(
        (VerdictDecision.DENY, VerdictDecision.DENY, VerdictDecision.DENY)
    )
    out = compute_consensus(cs, rs)
    assert out.kind == ConsensusKind.UNANIMOUS
    assert out.agreed_decision == VerdictDecision.DENY


def test_consensus_majority_allow_dissenter_c() -> None:
    cs, rs = _three_reveals(
        (VerdictDecision.ALLOW, VerdictDecision.ALLOW, VerdictDecision.DENY)
    )
    out = compute_consensus(cs, rs)
    assert out.kind == ConsensusKind.MAJORITY
    assert out.agreed_decision == VerdictDecision.ALLOW
    assert out.dissenters == (ReviewerId.REVIEWER_C,)


def test_consensus_majority_deny_dissenter_a() -> None:
    cs, rs = _three_reveals(
        (VerdictDecision.ALLOW, VerdictDecision.DENY, VerdictDecision.DENY)
    )
    out = compute_consensus(cs, rs)
    assert out.kind == ConsensusKind.MAJORITY
    assert out.agreed_decision == VerdictDecision.DENY
    assert out.dissenters == (ReviewerId.REVIEWER_A,)


def test_consensus_split_all_three_differ() -> None:
    cs, rs = _three_reveals(
        (VerdictDecision.ALLOW, VerdictDecision.DENY, VerdictDecision.ESCALATE)
    )
    out = compute_consensus(cs, rs)
    assert out.kind == ConsensusKind.SPLIT
    assert out.agreed_decision is None


def test_consensus_integrity_failure_tampered_reveal() -> None:
    cs, rs = _three_reveals(
        (VerdictDecision.ALLOW, VerdictDecision.ALLOW, VerdictDecision.ALLOW)
    )
    # Tamper with reviewer C's verdict after commitment was published.
    forged_c = _make_verdict(
        reviewer_id=ReviewerId.REVIEWER_C,
        decision=VerdictDecision.DENY,
    )
    rs_tampered = (rs[0], rs[1], (forged_c, rs[2][1]))
    out = compute_consensus(cs, rs_tampered)
    assert out.kind == ConsensusKind.INTEGRITY_FAILURE
    assert out.failed_reviewers == (ReviewerId.REVIEWER_C,)


def test_consensus_integrity_failure_missing_reveal() -> None:
    """Reveal set doesn't include all three reviewers -> integrity fail.

    Build commitments for A/B/C but reveal only A/B (with B repeated in
    the third slot to keep the tuple shape correct -- this means
    REVIEWER_C committed but never revealed)."""
    cs, rs = _three_reveals(
        (VerdictDecision.ALLOW, VerdictDecision.ALLOW, VerdictDecision.ALLOW)
    )
    rs_missing_c = (rs[0], rs[1], rs[1])  # third slot duplicates B
    out = compute_consensus(cs, rs_missing_c)
    assert out.kind == ConsensusKind.INTEGRITY_FAILURE
    assert ReviewerId.REVIEWER_C in out.failed_reviewers


# ---------------------------------------------------------------------------
# Layer 4 -- Hypothesis property tests
# ---------------------------------------------------------------------------


_decision_strategy = st.sampled_from(list(VerdictDecision))
_reviewer_strategy = st.sampled_from(list(ReviewerId))


@st.composite
def _verdict_strategy(draw):
    return ReviewerVerdict(
        reviewer_id=draw(_reviewer_strategy),
        decision=draw(_decision_strategy),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0)),
        reasoning=draw(st.text(max_size=64)),
        audit_id=draw(st.uuids()),
    )


@given(verdict=_verdict_strategy(), nonce=st.binary(min_size=NONCE_BYTES, max_size=NONCE_BYTES))
def test_property_commitment_round_trip(verdict, nonce) -> None:
    """Every (verdict, nonce) pair commits + reveals successfully."""
    c = compute_commitment(verdict, nonce)
    assert verify_reveal(c, verdict, nonce) is True


@given(verdict=_verdict_strategy(), nonce=st.binary(min_size=NONCE_BYTES, max_size=NONCE_BYTES))
def test_property_tampered_nonce_never_verifies(verdict, nonce) -> None:
    """Flipping any bit of the nonce breaks the binding."""
    c = compute_commitment(verdict, nonce)
    # Flip the first byte (any bit-flip would do).
    bad_nonce = bytes([nonce[0] ^ 0x01]) + nonce[1:]
    assert verify_reveal(c, verdict, bad_nonce) is False


@given(
    verdict_a=_verdict_strategy(),
    verdict_b=_verdict_strategy(),
    nonce=st.binary(min_size=NONCE_BYTES, max_size=NONCE_BYTES),
)
def test_property_distinct_verdicts_distinct_commitments(
    verdict_a, verdict_b, nonce
) -> None:
    """Two verdicts that canonicalise differently produce different
    commitments under the same nonce. (Tests SHA-256's collision
    resistance as a property over our domain.)"""
    if canonicalise_verdict(verdict_a) == canonicalise_verdict(verdict_b):
        return  # same canonical form -> same commitment (by design)
    c_a = compute_commitment(verdict_a, nonce)
    c_b = compute_commitment(verdict_b, nonce)
    # Commitments may share reviewer_id but should differ on hex.
    assert c_a.sha256_hex != c_b.sha256_hex
