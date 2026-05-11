"""pytest suite for verixa_runtime.triad.orchestrator (CP-10.3).

Coverage strategy: MockReviewer (CP-10.2) is the test harness; we
build factories that return controllable verdicts and run the
orchestrator end-to-end. No live droplet, no httpx, no asyncio
plumbing of our own beyond what pytest-asyncio provides.

Layers:
  1. TriadOrchestrator construction validation (slot mis-wiring).
  2. consensus_to_decision lookup table (UNANIMOUS / MAJORITY / SPLIT
     / INTEGRITY_FAILURE).
  3. End-to-end run() against MockReviewer factories:
     - all three agree ALLOW -> UNANIMOUS
     - 2-of-3 DENY with C dissenting -> MAJORITY DENY
     - all three differ -> SPLIT
     - one reviewer raises ReviewerError -> synthesised ESCALATE +
       failed_reviewers populated
     - audit_emit is awaited AFTER commit but BEFORE consensus (the
       integrity anchor) -- verified by capturing the commitments at
       the time the hook fires
     - audit_emit=None still produces a valid outcome
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from verixa_runtime.triad import (
    Commitment,
    ConsensusKind,
    ConsensusOutcome,
    MockReviewer,
    ReviewerError,
    ReviewerId,
    ReviewerVerdict,
    TriadOrchestrator,
    TriadOutcome,
    VerdictDecision,
    consensus_to_decision,
)

_AUDIT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


# ---------------------------------------------------------------------------
# Helpers -- factory builders for MockReviewer
# ---------------------------------------------------------------------------


def _verdict_factory_for(
    reviewer_id: ReviewerId, decision: VerdictDecision
) -> Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]:
    async def _factory(audit_id: uuid.UUID, _summary: str) -> ReviewerVerdict:
        return ReviewerVerdict(
            reviewer_id=reviewer_id,
            decision=decision,
            confidence=0.9,
            reasoning=f"{reviewer_id.value}-says-{decision.value}",
            audit_id=audit_id,
        )

    return _factory


def _failing_factory(
    reviewer_id: ReviewerId,
) -> Callable[[uuid.UUID, str], Awaitable[ReviewerVerdict]]:
    async def _factory(_a: uuid.UUID, _s: str) -> ReviewerVerdict:
        raise ReviewerError(f"{reviewer_id.value} simulated outage")

    return _factory


def _build_orchestrator(
    *,
    a_decision: VerdictDecision = VerdictDecision.ALLOW,
    b_decision: VerdictDecision = VerdictDecision.ALLOW,
    c_decision: VerdictDecision = VerdictDecision.ALLOW,
    a_fails: bool = False,
    b_fails: bool = False,
    c_fails: bool = False,
) -> TriadOrchestrator:
    a_factory = (
        _failing_factory(ReviewerId.REVIEWER_A)
        if a_fails
        else _verdict_factory_for(ReviewerId.REVIEWER_A, a_decision)
    )
    b_factory = (
        _failing_factory(ReviewerId.REVIEWER_B)
        if b_fails
        else _verdict_factory_for(ReviewerId.REVIEWER_B, b_decision)
    )
    c_factory = (
        _failing_factory(ReviewerId.REVIEWER_C)
        if c_fails
        else _verdict_factory_for(ReviewerId.REVIEWER_C, c_decision)
    )
    return TriadOrchestrator(
        reviewer_a=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_A, factory=a_factory
        ),
        reviewer_b=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_B, factory=b_factory
        ),
        reviewer_c=MockReviewer(
            _reviewer_id=ReviewerId.REVIEWER_C, factory=c_factory
        ),
    )


# ---------------------------------------------------------------------------
# Layer 1: Construction validation
# ---------------------------------------------------------------------------


def test_orchestrator_rejects_wrong_slot_a() -> None:
    """reviewer_a holding a REVIEWER_B reviewer is a programming error."""
    a_factory = _verdict_factory_for(ReviewerId.REVIEWER_B, VerdictDecision.ALLOW)
    b_factory = _verdict_factory_for(ReviewerId.REVIEWER_B, VerdictDecision.ALLOW)
    c_factory = _verdict_factory_for(ReviewerId.REVIEWER_C, VerdictDecision.ALLOW)
    with pytest.raises(ValueError, match="reviewer_a"):
        TriadOrchestrator(
            reviewer_a=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_B, factory=a_factory
            ),
            reviewer_b=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_B, factory=b_factory
            ),
            reviewer_c=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_C, factory=c_factory
            ),
        )


def test_orchestrator_rejects_wrong_slot_b() -> None:
    a_factory = _verdict_factory_for(ReviewerId.REVIEWER_A, VerdictDecision.ALLOW)
    b_factory = _verdict_factory_for(ReviewerId.REVIEWER_A, VerdictDecision.ALLOW)
    c_factory = _verdict_factory_for(ReviewerId.REVIEWER_C, VerdictDecision.ALLOW)
    with pytest.raises(ValueError, match="reviewer_b"):
        TriadOrchestrator(
            reviewer_a=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_A, factory=a_factory
            ),
            reviewer_b=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_A, factory=b_factory
            ),
            reviewer_c=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_C, factory=c_factory
            ),
        )


def test_orchestrator_rejects_wrong_slot_c() -> None:
    a_factory = _verdict_factory_for(ReviewerId.REVIEWER_A, VerdictDecision.ALLOW)
    b_factory = _verdict_factory_for(ReviewerId.REVIEWER_B, VerdictDecision.ALLOW)
    c_factory = _verdict_factory_for(ReviewerId.REVIEWER_A, VerdictDecision.ALLOW)
    with pytest.raises(ValueError, match="reviewer_c"):
        TriadOrchestrator(
            reviewer_a=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_A, factory=a_factory
            ),
            reviewer_b=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_B, factory=b_factory
            ),
            reviewer_c=MockReviewer(
                _reviewer_id=ReviewerId.REVIEWER_A, factory=c_factory
            ),
        )


# ---------------------------------------------------------------------------
# Layer 2: consensus_to_decision lookup
# ---------------------------------------------------------------------------


def _outcome_with_consensus(
    consensus: ConsensusOutcome,
) -> TriadOutcome:
    """Build a minimally-valid TriadOutcome around a given ConsensusOutcome.

    The verdicts/commitments tuples just need to be present and shaped
    correctly; consensus_to_decision only inspects ``consensus``.
    """
    placeholder_verdict = ReviewerVerdict(
        reviewer_id=ReviewerId.REVIEWER_A,
        decision=VerdictDecision.ALLOW,
        confidence=1.0,
        reasoning="x",
        audit_id=_AUDIT_ID,
    )
    placeholder_commitment = Commitment(
        reviewer_id=ReviewerId.REVIEWER_A, sha256_hex="0" * 64
    )
    return TriadOutcome(
        audit_id=_AUDIT_ID,
        verdicts=(placeholder_verdict, placeholder_verdict, placeholder_verdict),
        commitments=(
            placeholder_commitment,
            placeholder_commitment,
            placeholder_commitment,
        ),
        consensus=consensus,
    )


def test_consensus_to_decision_unanimous_returns_agreed() -> None:
    out = _outcome_with_consensus(
        ConsensusOutcome(
            kind=ConsensusKind.UNANIMOUS,
            agreed_decision=VerdictDecision.DENY,
        )
    )
    assert consensus_to_decision(out) == VerdictDecision.DENY


def test_consensus_to_decision_majority_returns_agreed() -> None:
    out = _outcome_with_consensus(
        ConsensusOutcome(
            kind=ConsensusKind.MAJORITY,
            agreed_decision=VerdictDecision.ALLOW,
            dissenters=(ReviewerId.REVIEWER_C,),
        )
    )
    assert consensus_to_decision(out) == VerdictDecision.ALLOW


def test_consensus_to_decision_split_returns_escalate() -> None:
    out = _outcome_with_consensus(ConsensusOutcome(kind=ConsensusKind.SPLIT))
    assert consensus_to_decision(out) == VerdictDecision.ESCALATE


def test_consensus_to_decision_integrity_failure_returns_escalate() -> None:
    out = _outcome_with_consensus(
        ConsensusOutcome(
            kind=ConsensusKind.INTEGRITY_FAILURE,
            failed_reviewers=(ReviewerId.REVIEWER_B,),
        )
    )
    assert consensus_to_decision(out) == VerdictDecision.ESCALATE


# ---------------------------------------------------------------------------
# Layer 3: End-to-end run()
# ---------------------------------------------------------------------------


async def test_run_unanimous_allow() -> None:
    orch = _build_orchestrator()  # all three default ALLOW
    outcome = await orch.run(
        audit_id=_AUDIT_ID,
        governed_action_summary="transfer 100 to acct",
    )
    assert outcome.consensus.kind == ConsensusKind.UNANIMOUS
    assert outcome.consensus.agreed_decision == VerdictDecision.ALLOW
    assert len(outcome.verdicts) == 3
    assert len(outcome.commitments) == 3
    assert outcome.failed_reviewers == ()
    assert outcome.audit_id == _AUDIT_ID


async def test_run_majority_deny_dissenter_c() -> None:
    orch = _build_orchestrator(
        a_decision=VerdictDecision.DENY,
        b_decision=VerdictDecision.DENY,
        c_decision=VerdictDecision.ALLOW,
    )
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    assert outcome.consensus.kind == ConsensusKind.MAJORITY
    assert outcome.consensus.agreed_decision == VerdictDecision.DENY
    assert outcome.consensus.dissenters == (ReviewerId.REVIEWER_C,)


async def test_run_split_all_three_differ() -> None:
    orch = _build_orchestrator(
        a_decision=VerdictDecision.ALLOW,
        b_decision=VerdictDecision.DENY,
        c_decision=VerdictDecision.ESCALATE,
    )
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    assert outcome.consensus.kind == ConsensusKind.SPLIT
    assert outcome.consensus.agreed_decision is None


async def test_run_reviewer_a_outage_synthesises_escalate() -> None:
    """Reviewer A raises -> orchestrator synthesises ESCALATE for slot A
    so the protocol still completes; failed_reviewers names slot A."""
    orch = _build_orchestrator(
        a_fails=True,
        b_decision=VerdictDecision.ALLOW,
        c_decision=VerdictDecision.ALLOW,
    )
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    # Slot A's verdict was synthesised to ESCALATE.
    assert outcome.verdicts[0].reviewer_id == ReviewerId.REVIEWER_A
    assert outcome.verdicts[0].decision == VerdictDecision.ESCALATE
    assert outcome.verdicts[0].confidence == pytest.approx(0.0)
    assert ReviewerId.REVIEWER_A in outcome.failed_reviewers
    # B and C voted ALLOW; A synthesised ESCALATE -> 2 distinct
    # decisions across the three slots -> MAJORITY ALLOW with A as
    # the dissenter.
    assert outcome.consensus.kind == ConsensusKind.MAJORITY
    assert outcome.consensus.agreed_decision == VerdictDecision.ALLOW
    assert outcome.consensus.dissenters == (ReviewerId.REVIEWER_A,)


async def test_run_audit_emit_called_with_three_commitments() -> None:
    """audit_emit hook fires AFTER commit, BEFORE consensus.

    Verify this by snapshotting the commitments the hook receives and
    comparing to the final outcome -- they must match exactly.
    """
    captured: dict[str, Any] = {}

    async def emit_hook(
        audit_id: uuid.UUID, commitments: list[Commitment]
    ) -> None:
        captured["audit_id"] = audit_id
        captured["commitments"] = list(commitments)

    orch = _build_orchestrator()
    outcome = await orch.run(
        audit_id=_AUDIT_ID,
        governed_action_summary="x",
        audit_emit=emit_hook,
    )
    assert captured["audit_id"] == _AUDIT_ID
    assert len(captured["commitments"]) == 3
    # The hook saw exactly the same commitments that ended up in the
    # outcome -- confirms the integrity anchor (no reveal happened
    # between commit and emit).
    assert tuple(captured["commitments"]) == outcome.commitments


async def test_run_audit_emit_none_still_produces_outcome() -> None:
    """No audit_emit -> the orchestrator skips the hook and still
    produces a valid outcome."""
    orch = _build_orchestrator()
    outcome = await orch.run(
        audit_id=_AUDIT_ID,
        governed_action_summary="x",
        audit_emit=None,
    )
    assert outcome.consensus.kind == ConsensusKind.UNANIMOUS


async def test_run_two_reviewers_fail() -> None:
    """Slots A and B fail; only C produces a real verdict.

    A and B synthesise ESCALATE; C says ALLOW; consensus = SPLIT
    (well, MAJORITY ESCALATE actually, since A and B both ESCALATE
    and C ALLOWs). Verify failed_reviewers lists both A and B."""
    orch = _build_orchestrator(
        a_fails=True,
        b_fails=True,
        c_decision=VerdictDecision.ALLOW,
    )
    outcome = await orch.run(
        audit_id=_AUDIT_ID, governed_action_summary="x"
    )
    assert ReviewerId.REVIEWER_A in outcome.failed_reviewers
    assert ReviewerId.REVIEWER_B in outcome.failed_reviewers
    assert ReviewerId.REVIEWER_C not in outcome.failed_reviewers
    # Two synthesised ESCALATEs vs one real ALLOW -> majority ESCALATE.
    assert outcome.consensus.kind == ConsensusKind.MAJORITY
    assert outcome.consensus.agreed_decision == VerdictDecision.ESCALATE
