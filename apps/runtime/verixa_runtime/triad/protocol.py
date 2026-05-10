"""Triad commit-reveal protocol primitives (CP-10.1).

Pure-function module. No I/O dependencies. Implements:

  - VerdictDecision enum (allow/deny/escalate)
  - ReviewerId enum (REVIEWER_A, REVIEWER_B, REVIEWER_C)
  - ReviewerVerdict frozen dataclass (decision, confidence, reasoning)
  - Commitment frozen dataclass (reviewer_id, sha256_hex)
  - canonicalise_verdict -- deterministic byte serialisation for hashing
  - generate_nonce -- 32 bytes from os.urandom
  - compute_commitment -- SHA-256(canonical(verdict) || nonce)
  - verify_reveal -- recompute and compare in constant time
  - compute_consensus -- 3-of-3 / 2-of-3 / split classifier

Integrity is anchored on SHA-256 (CP-4 hashing). The audit emitter
(CP-5) signs the *list of commitments* so that the on-chain trail
shows three commitments published before any reveal occurred.
"""

from __future__ import annotations

import hmac
import json
import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Final


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class VerdictDecision(str, Enum):
    """Reviewer verdict outcome.

    Mirrors the gateway-level Decision enum but lives separately so the
    triad protocol stays independent of the response envelope.
    """

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class ReviewerId(str, Enum):
    """Stable identifiers for the three reviewer slots.

    The mapping from slot to actual model is configured at the
    orchestrator layer (CP-10.3); this layer only cares that there
    are exactly three distinct reviewers.
    """

    REVIEWER_A = "reviewer_a"
    REVIEWER_B = "reviewer_b"
    REVIEWER_C = "reviewer_c"


class ConsensusKind(str, Enum):
    """How well the three reviewers agreed.

    UNANIMOUS  -- all three verdict.decision equal. Full confidence;
                  return the agreed decision.
    MAJORITY   -- two reviewers agree, one differs. Acceptable for
                  ALLOW / DENY but the dissenter is flagged for
                  drift-monitoring (CP-? Phase 1).
    SPLIT      -- all three differ. Cannot return a decision; the
                  governed action escalates to human review.
    INTEGRITY_FAILURE -- one or more reveals failed to match their
                  commitment. Treated as protocol abort: escalate and
                  flag the offending reviewer.
    """

    UNANIMOUS = "unanimous"
    MAJORITY = "majority"
    SPLIT = "split"
    INTEGRITY_FAILURE = "integrity_failure"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


# Nonce length in bytes. 32 bytes = 256 bits = SHA-256 collision-resistance
# domain. Reviewers MUST sample from os.urandom; predictable nonces let
# an attacker forge a different verdict that still hashes to the same
# commitment (extremely hard but not the goal -- the goal is
# unconditional binding, so we use full collision-resistance margin).
NONCE_BYTES: Final[int] = 32


@dataclass(frozen=True, slots=True)
class ReviewerVerdict:
    """A reviewer's verdict on a single governed action.

    ``decision`` is the only field used for consensus computation;
    ``confidence`` and ``reasoning`` are preserved for the audit trail
    and for human reviewers inspecting an escalation, but they do not
    flip the consensus outcome.
    """

    reviewer_id: ReviewerId
    decision: VerdictDecision
    confidence: float
    reasoning: str
    audit_id: uuid.UUID

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0.0, 1.0]; got {self.confidence!r}"
            )


@dataclass(frozen=True, slots=True)
class Commitment:
    """SHA-256 commitment to a verdict + nonce.

    The on-chain audit row carries (reviewer_id, sha256_hex,
    audit_id_of_committed_verdict) so a third party can later replay
    the reveal and verify the binding.
    """

    reviewer_id: ReviewerId
    sha256_hex: str

    def __post_init__(self) -> None:
        if len(self.sha256_hex) != 64 or not all(
            c in "0123456789abcdef" for c in self.sha256_hex
        ):
            raise ValueError(
                f"sha256_hex must be 64 lowercase hex chars; got {self.sha256_hex!r}"
            )


@dataclass(frozen=True, slots=True)
class ConsensusOutcome:
    """Result of running compute_consensus over three reveals.

    If ``kind`` is UNANIMOUS or MAJORITY, ``agreed_decision`` is the
    decision the majority/all chose. If SPLIT, ``agreed_decision`` is
    None. If INTEGRITY_FAILURE, ``agreed_decision`` is None and
    ``failed_reviewers`` lists which reviewers' reveals didn't bind.
    """

    kind: ConsensusKind
    agreed_decision: VerdictDecision | None = None
    dissenters: tuple[ReviewerId, ...] = field(default_factory=tuple)
    failed_reviewers: tuple[ReviewerId, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Protocol primitives
# ---------------------------------------------------------------------------


def canonicalise_verdict(verdict: ReviewerVerdict) -> bytes:
    """Deterministic byte serialisation of a verdict.

    Consensus and commitment binding both depend on the *exact same
    bytes* coming out of canonicalisation regardless of dict-insertion
    order or JSON whitespace. Uses sorted-keys + minimal separators.

    The audit_id is included because two reviewers might happen to
    produce the same (decision, confidence, reasoning) tuple on
    *different* governed actions -- the audit_id distinguishes them
    so a commitment from one action can't be replayed on another.
    """
    payload = {
        "reviewer_id": verdict.reviewer_id.value,
        "decision": verdict.decision.value,
        "confidence": verdict.confidence,
        "reasoning": verdict.reasoning,
        "audit_id": str(verdict.audit_id),
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def generate_nonce() -> bytes:
    """Return a fresh cryptographically-strong 32-byte nonce.

    Wraps os.urandom so callers can mock at the seam without touching
    the os module. NEVER use predictable values (counter, timestamp);
    a leaked nonce-generation seed lets an attacker forge a different
    verdict that hashes to the same commitment.
    """
    return os.urandom(NONCE_BYTES)


def compute_commitment(
    verdict: ReviewerVerdict, nonce: bytes
) -> Commitment:
    """SHA-256(canonical(verdict) || nonce) as a Commitment.

    Raises ValueError if nonce length is wrong (defence against
    accidentally passing a string or a truncated buffer).
    """
    if len(nonce) != NONCE_BYTES:
        raise ValueError(
            f"nonce must be exactly {NONCE_BYTES} bytes; got {len(nonce)}"
        )
    digest = sha256(canonicalise_verdict(verdict) + nonce).hexdigest()
    return Commitment(reviewer_id=verdict.reviewer_id, sha256_hex=digest)


def verify_reveal(
    commitment: Commitment, verdict: ReviewerVerdict, nonce: bytes
) -> bool:
    """Constant-time comparison of recomputed digest to the commitment.

    Uses hmac.compare_digest so a partial-match attacker can't time
    the call to reverse-engineer the digest one byte at a time.
    Returns True on match (binding holds), False otherwise.

    Also enforces the reviewer_id matches: a commitment from
    REVIEWER_A cannot be revealed as REVIEWER_B's verdict (defence
    against label-swap attack at the orchestrator layer).
    """
    if commitment.reviewer_id != verdict.reviewer_id:
        return False
    if len(nonce) != NONCE_BYTES:
        return False
    recomputed = sha256(canonicalise_verdict(verdict) + nonce).hexdigest()
    return hmac.compare_digest(recomputed, commitment.sha256_hex)


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------


def compute_consensus(
    commitments: tuple[Commitment, Commitment, Commitment],
    reveals: tuple[
        tuple[ReviewerVerdict, bytes],
        tuple[ReviewerVerdict, bytes],
        tuple[ReviewerVerdict, bytes],
    ],
) -> ConsensusOutcome:
    """Verify reveals against commitments, then classify consensus.

    Inputs:
      - ``commitments``: the three on-chain commitments (one per
        ReviewerId; order matches the orchestrator's slot ordering).
      - ``reveals``: parallel tuple of (verdict, nonce) per reviewer.

    Pre-condition: the orchestrator has already paired commitments
    with their corresponding reveals by reviewer_id (the orchestrator
    knows which reviewer each commitment came from). This function
    enforces that pairing again as defence-in-depth.

    Output:
      - INTEGRITY_FAILURE if any reveal fails to bind, with the
        offending reviewer ids in failed_reviewers.
      - UNANIMOUS / MAJORITY / SPLIT otherwise, with the agreed
        decision (where one exists) and the dissenters list.
    """
    # Pair each commitment with the matching reveal by reviewer_id.
    # If any reviewer is missing or duplicated, that's a protocol
    # error -- treat it as integrity failure naming the orphans.
    commit_by_id = {c.reviewer_id: c for c in commitments}
    reveal_by_id: dict[ReviewerId, tuple[ReviewerVerdict, bytes]] = {}
    for verdict, nonce in reveals:
        reveal_by_id[verdict.reviewer_id] = (verdict, nonce)

    if set(commit_by_id.keys()) != set(reveal_by_id.keys()):
        # Mismatch in which reviewers committed vs. revealed -- mark
        # any reviewer that committed but didn't reveal as failed.
        missing = set(commit_by_id.keys()) - set(reveal_by_id.keys())
        return ConsensusOutcome(
            kind=ConsensusKind.INTEGRITY_FAILURE,
            failed_reviewers=tuple(sorted(missing, key=lambda r: r.value)),
        )

    # Verify every reveal binds to its commitment.
    failed: list[ReviewerId] = []
    for rid, commitment in commit_by_id.items():
        verdict, nonce = reveal_by_id[rid]
        if not verify_reveal(commitment, verdict, nonce):
            failed.append(rid)

    if failed:
        return ConsensusOutcome(
            kind=ConsensusKind.INTEGRITY_FAILURE,
            failed_reviewers=tuple(sorted(failed, key=lambda r: r.value)),
        )

    # Tally the three decisions.
    decisions = [reveal_by_id[rid][0].decision for rid in commit_by_id]
    distinct = set(decisions)

    if len(distinct) == 1:
        return ConsensusOutcome(
            kind=ConsensusKind.UNANIMOUS,
            agreed_decision=decisions[0],
        )

    if len(distinct) == 3:
        # All three differ -- no decision wins.
        return ConsensusOutcome(kind=ConsensusKind.SPLIT)

    # Exactly two distinct decisions -> 2-of-3 majority.
    # Find which decision has count 2 and which reviewer dissented.
    counts: dict[VerdictDecision, int] = {}
    for d in decisions:
        counts[d] = counts.get(d, 0) + 1
    majority_decision = max(counts, key=lambda d: counts[d])
    dissenters = tuple(
        sorted(
            (rid for rid in commit_by_id
             if reveal_by_id[rid][0].decision != majority_decision),
            key=lambda r: r.value,
        )
    )
    return ConsensusOutcome(
        kind=ConsensusKind.MAJORITY,
        agreed_decision=majority_decision,
        dissenters=dissenters,
    )
