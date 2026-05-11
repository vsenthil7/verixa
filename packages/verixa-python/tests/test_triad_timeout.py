"""CP-30 negative test 1/5: triad reviewer timeout + outage edges.

Anchored to UC-04 (triad escalation), BR-03 (independent multi-reviewer
consensus), NEGATIVE_TEST_PLAN section 3 (triad failure modes).

The triad orchestrator MUST NOT hang or panic when a reviewer:
  - raises asyncio.TimeoutError mid-call
  - raises a generic ReviewerError (already covered by
    test_triad_orchestrator.py for slot A; this file covers all three
    slots plus the all-three-fail edge)

The expected behaviour for every timeout/outage:
  - Failed slot synthesises ReviewerVerdict(decision=ESCALATE,
    confidence=0.0)
  - outcome.failed_reviewers contains the failing slot(s)
  - The remaining slots produce real verdicts that are counted
    normally
  - consensus_to_decision() returns ESCALATE if the synthesised
    verdicts dominate, else MAJORITY agreed_decision

Adversarial framing: these tests model what happens when an MI300X
reviewer droplet stalls or returns 504. The protocol must degrade
to ESCALATE, never to an accidental ALLOW or DENY.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from verixa_runtime.triad import (
    ConsensusKind,
    MockReviewer,
    ReviewerError,
    ReviewerId,
    ReviewerVerdict,
    TriadOrchestrator,
    VerdictDecision,
    consensus_to_decision,
)

_AUDIT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allow_factory(
    reviewer_id: ReviewerId,
) -> Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]:
    async def _factory(audit_id: uuid.UUID, _summary: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=reviewer_id,
            decision=VerdictDecision.ALLOW,
            confidence=0.9,
            reasoning=f"{reviewer_id.value}-allow",
            audit_id=audit_id,
        )

    return _factory


def _timeout_factory(
    reviewer_id: ReviewerId,
) -> Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]:
    """Factory that raises ReviewerError wrapping an asyncio.TimeoutError
    to simulate a stalled reviewer hitting an upstream deadline."""

    async def _factory(_a: uuid.UUID, _s: str) -> ReviewerVerdict:
        try:
            raise TimeoutError("reviewer deadline 5s exceeded")
        except TimeoutError as exc:
            raise ReviewerError(
                f"{reviewer_id.value} timed out: {exc}"
            ) from exc

    return _factory


def _build_orchestrator(
    *,
    a_factory: Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]] | None = None,
    b_factory: Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]] | None = None,
    c_factory: Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]] | None = None,
) -> TriadOrchestrator:
    return TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A,
            factory=a_factory or _allow_factory(ReviewerId.REVIEWER_A),
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B,
            factory=b_factory or _allow_factory(ReviewerId.REVIEWER_B),
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C,
            factory=c_factory or _allow_factory(ReviewerId.REVIEWER_C),
        ),
    )


# ---------------------------------------------------------------------------
# Single-slot timeout edges (A, B, C)
# ---------------------------------------------------------------------------


async def test_slot_a_timeout_synthesises_escalate() -> None:
    """A times out; B and C ALLOW. A's slot must show ESCALATE+0.0
    confidence and the consensus must be MAJORITY ALLOW (B+C real
    ALLOW vs A's synthesised ESCALATE)."""
    orch = _build_orchestrator(a_factory=_timeout_factory(ReviewerId.REVIEWER_A))
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="transfer 500"
    )
    assert outcome.verdicts[0].reviewer_id == ReviewerId.REVIEWER_A
    assert outcome.verdicts[0].decision == VerdictDecision.ESCALATE
    assert outcome.verdicts[0].confidence == pytest.approx(0.0)
    assert ReviewerId.REVIEWER_A in outcome.failed_reviewers
    assert outcome.consensus.kind == ConsensusKind.MAJORITY
    assert outcome.consensus.agreed_decision == VerdictDecision.ALLOW
    assert ReviewerId.REVIEWER_A in outcome.consensus.dissenters


async def test_slot_b_timeout_synthesises_escalate() -> None:
    """B times out; A and C ALLOW."""
    orch = _build_orchestrator(b_factory=_timeout_factory(ReviewerId.REVIEWER_B))
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    assert outcome.verdicts[1].reviewer_id == ReviewerId.REVIEWER_B
    assert outcome.verdicts[1].decision == VerdictDecision.ESCALATE
    assert ReviewerId.REVIEWER_B in outcome.failed_reviewers
    assert outcome.consensus.kind == ConsensusKind.MAJORITY
    assert outcome.consensus.agreed_decision == VerdictDecision.ALLOW


async def test_slot_c_timeout_synthesises_escalate() -> None:
    """C times out; A and B ALLOW."""
    orch = _build_orchestrator(c_factory=_timeout_factory(ReviewerId.REVIEWER_C))
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    assert outcome.verdicts[2].reviewer_id == ReviewerId.REVIEWER_C
    assert outcome.verdicts[2].decision == VerdictDecision.ESCALATE
    assert ReviewerId.REVIEWER_C in outcome.failed_reviewers
    assert outcome.consensus.kind == ConsensusKind.MAJORITY


# ---------------------------------------------------------------------------
# Multi-slot outages
# ---------------------------------------------------------------------------


async def test_all_three_reviewers_time_out() -> None:
    """All three time out. Every slot synthesises ESCALATE; the
    consensus is UNANIMOUS ESCALATE. The action MUST NOT slip through
    to a default ALLOW even when no real verdicts arrived."""
    orch = _build_orchestrator(
        a_factory=_timeout_factory(ReviewerId.REVIEWER_A),
        b_factory=_timeout_factory(ReviewerId.REVIEWER_B),
        c_factory=_timeout_factory(ReviewerId.REVIEWER_C),
    )
    outcome = await orch.run(
        audit_id=_AUDIT_ID,
        governed_action_summary="transfer 1000000 to attacker",
    )
    # Every slot is failed.
    assert set(outcome.failed_reviewers) == {
        ReviewerId.REVIEWER_A,
        ReviewerId.REVIEWER_B,
        ReviewerId.REVIEWER_C,
    }
    # Every synthesised verdict is ESCALATE.
    for v in outcome.verdicts:
        assert v.decision == VerdictDecision.ESCALATE
        assert v.confidence == pytest.approx(0.0)
    # Three ESCALATEs agree -> UNANIMOUS ESCALATE.
    assert outcome.consensus.kind == ConsensusKind.UNANIMOUS
    assert outcome.consensus.agreed_decision == VerdictDecision.ESCALATE
    # And the routing decision is ESCALATE, NOT ALLOW.
    assert consensus_to_decision(outcome) == VerdictDecision.ESCALATE


async def test_two_of_three_time_out_one_says_deny() -> None:
    """A and B time out; C says DENY. Two synthesised ESCALATEs vs one
    real DENY -> majority ESCALATE; routing decision ESCALATE.

    Adversarial scenario: this models the worst case where an
    attacker correlates outages with a borderline action -- even
    then, the protocol degrades safely to ESCALATE (human review),
    NEVER to ALLOW."""

    async def _deny_c(audit_id: uuid.UUID, _s: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=ReviewerId.REVIEWER_C,
            decision=VerdictDecision.DENY,
            confidence=0.95,
            reasoning="c-deny",
            audit_id=audit_id,
        )

    orch = _build_orchestrator(
        a_factory=_timeout_factory(ReviewerId.REVIEWER_A),
        b_factory=_timeout_factory(ReviewerId.REVIEWER_B),
        c_factory=_deny_c,
    )
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    assert ReviewerId.REVIEWER_A in outcome.failed_reviewers
    assert ReviewerId.REVIEWER_B in outcome.failed_reviewers
    assert ReviewerId.REVIEWER_C not in outcome.failed_reviewers
    # Two ESCALATEs (A, B synthesised) vs one DENY (C real) -> majority
    # ESCALATE.
    assert outcome.consensus.kind == ConsensusKind.MAJORITY
    assert outcome.consensus.agreed_decision == VerdictDecision.ESCALATE
    # Critical: an ALLOW must never emerge from a timeout-storm.
    assert consensus_to_decision(outcome) != VerdictDecision.ALLOW
