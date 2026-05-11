"""Triad orchestrator (CP-10.3).

Runs the commit-reveal protocol across three reviewers in parallel.

Phases:
  1. **Review.** asyncio.gather over the three Reviewer.review() calls.
     Each reviewer produces a ReviewerVerdict (or raises ReviewerError,
     which the orchestrator converts to a synthesised ESCALATE verdict
     so partial-triad outages still produce a well-formed audit trail).
  2. **Commit.** For each successful verdict, generate a fresh nonce
     and compute a Commitment. The list of three commitments is
     "published" (the audit-emit hook is wired in CP-10.5; this module
     accepts an optional ``audit_emit`` callable so the gateway can
     persist the commitments before any reveal).
  3. **Reveal.** Pair each commitment with its (verdict, nonce) and
     run compute_consensus from CP-10.1.

The orchestrator returns a TriadOutcome that bundles the reviewer
verdicts, the commitments, and the consensus result. Downstream
(CP-10.5) the gateway turns this into the GovernResponse fields:
  - UNANIMOUS or MAJORITY -> the agreed decision flips R3 ESCALATE
    to whatever the triad decided (allow/deny/escalate)
  - SPLIT or INTEGRITY_FAILURE -> stays ESCALATE, surfaces in
    triad_consensus = "split"/"integrity_failure"

The orchestrator is entirely async and does NO blocking I/O of its
own; the underlying Reviewer.review() implementations may do HTTP
(OpenAICompatReviewer) or be in-memory (MockReviewer).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Final

from verixa_runtime.triad.protocol import (
    Commitment,
    ConsensusKind,
    ConsensusOutcome,
    ReviewerId,
    ReviewerVerdict,
    VerdictDecision,
    compute_commitment,
    compute_consensus,
    generate_nonce,
)
from verixa_runtime.triad.reviewer import Reviewer, ReviewerError

# Synthesised reasoning text for verdicts that stand in for a reviewer
# that crashed; surfaced verbatim in the audit trail so it's clear to
# a human reviewer that this slot did NOT actually produce a verdict.
_REVIEWER_OUTAGE_REASONING: Final[str] = (
    "reviewer-outage-synthesised-escalate"
)

# Audit-emit callable: the gateway-supplied hook that persists the
# three commitments to the audit ledger BEFORE any reveal phase. The
# callable signature mirrors the audit emitter from CP-5; here we
# just accept "anything async-callable that takes a list of
# Commitment + audit_id". CP-10.5 wires the real audit emitter.
AuditEmitCommitments = Callable[
    [uuid.UUID, list[Commitment]], Awaitable[None]
]


@dataclass(frozen=True, slots=True)
class TriadOutcome:
    """Bundle returned to the gateway.

    ``verdicts`` -- exactly three, indexed by reviewer slot order
                    (REVIEWER_A, _B, _C).
    ``commitments`` -- the three commitments, parallel to verdicts,
                       in the same slot order.
    ``consensus`` -- result of compute_consensus.
    ``failed_reviewers`` -- reviewers that errored during the review
                            phase; their verdicts are synthesised
                            ESCALATEs and they're flagged for
                            drift-monitoring downstream.
    """

    audit_id: uuid.UUID
    verdicts: tuple[ReviewerVerdict, ReviewerVerdict, ReviewerVerdict]
    commitments: tuple[Commitment, Commitment, Commitment]
    consensus: ConsensusOutcome
    failed_reviewers: tuple[ReviewerId, ...] = field(default_factory=tuple)


def _synthesise_outage_verdict(
    reviewer_id: ReviewerId, audit_id: uuid.UUID
) -> ReviewerVerdict:
    """Stand-in verdict when a reviewer raises ReviewerError.

    decision=ESCALATE so the triad won't treat it as a passing vote;
    confidence=0.0 so any drift-monitoring downstream sees this as
    explicitly-no-signal.
    """
    return ReviewerVerdict(
        reviewer_id=reviewer_id,
        decision=VerdictDecision.ESCALATE,
        confidence=0.0,
        reasoning=_REVIEWER_OUTAGE_REASONING,
        audit_id=audit_id,
    )


async def _safe_review(
    reviewer: Reviewer,
    *,
    audit_id: uuid.UUID,
    governed_action_summary: str,
) -> tuple[ReviewerVerdict, bool]:
    """Run a single reviewer; return (verdict, errored).

    On ReviewerError or any unexpected exception, synthesise an
    outage verdict so the orchestrator can still complete the
    protocol and the gateway gets a well-formed audit trail.
    """
    try:
        v = await reviewer.review(
            audit_id=audit_id,
            governed_action_summary=governed_action_summary,
        )
    except ReviewerError:
        return _synthesise_outage_verdict(reviewer.reviewer_id, audit_id), True
    except Exception:  # pragma: no cover -- defence-in-depth catch-all
        # We log nothing here intentionally; the orchestrator is pure
        # logic and CP-10.5 will add structured-log emission at the
        # gateway integration seam. The audit trail surfaces the
        # synthesised verdict.
        return _synthesise_outage_verdict(reviewer.reviewer_id, audit_id), True
    return v, False


@dataclass(frozen=True, slots=True)
class TriadOrchestrator:
    """Runs commit-reveal across exactly three reviewers."""

    reviewer_a: Reviewer
    reviewer_b: Reviewer
    reviewer_c: Reviewer

    def __post_init__(self) -> None:
        # Pull reviewer_ids and check they're the expected slot mapping
        # AND distinct. Mis-wiring at construction is a programming
        # error, not a runtime concern, so we raise eagerly.
        a, b, c = (
            self.reviewer_a.reviewer_id,
            self.reviewer_b.reviewer_id,
            self.reviewer_c.reviewer_id,
        )
        if a != ReviewerId.REVIEWER_A:
            raise ValueError(
                f"reviewer_a.reviewer_id must be REVIEWER_A; got {a.value}"
            )
        if b != ReviewerId.REVIEWER_B:
            raise ValueError(
                f"reviewer_b.reviewer_id must be REVIEWER_B; got {b.value}"
            )
        if c != ReviewerId.REVIEWER_C:
            raise ValueError(
                f"reviewer_c.reviewer_id must be REVIEWER_C; got {c.value}"
            )

    async def run(
        self,
        *,
        audit_id: uuid.UUID,
        governed_action_summary: str,
        audit_emit: AuditEmitCommitments | None = None,
    ) -> TriadOutcome:
        """Run the protocol; return a TriadOutcome.

        If ``audit_emit`` is provided, it is awaited AFTER the three
        commitments are computed but BEFORE the reveal/consensus step.
        This is the integrity anchor: by the time consensus runs, the
        commitments are durably recorded so a third party can replay
        the binding later.
        """
        # Phase 1: review (parallel).
        results = await asyncio.gather(
            _safe_review(
                self.reviewer_a,
                audit_id=audit_id,
                governed_action_summary=governed_action_summary,
            ),
            _safe_review(
                self.reviewer_b,
                audit_id=audit_id,
                governed_action_summary=governed_action_summary,
            ),
            _safe_review(
                self.reviewer_c,
                audit_id=audit_id,
                governed_action_summary=governed_action_summary,
            ),
        )
        verdicts: tuple[
            ReviewerVerdict, ReviewerVerdict, ReviewerVerdict
        ] = (results[0][0], results[1][0], results[2][0])
        failed = tuple(
            v.reviewer_id for v, errored in results if errored
        )

        # Phase 2: commit.
        nonces = (generate_nonce(), generate_nonce(), generate_nonce())
        commitments: tuple[Commitment, Commitment, Commitment] = (
            compute_commitment(verdicts[0], nonces[0]),
            compute_commitment(verdicts[1], nonces[1]),
            compute_commitment(verdicts[2], nonces[2]),
        )

        # Audit-emit hook fires AFTER commit, BEFORE reveal/consensus.
        if audit_emit is not None:
            await audit_emit(audit_id, list(commitments))

        # Phase 3: reveal + consensus.
        reveals = (
            (verdicts[0], nonces[0]),
            (verdicts[1], nonces[1]),
            (verdicts[2], nonces[2]),
        )
        consensus = compute_consensus(commitments, reveals)

        return TriadOutcome(
            audit_id=audit_id,
            verdicts=verdicts,
            commitments=commitments,
            consensus=consensus,
            failed_reviewers=failed,
        )


def consensus_to_decision(
    outcome: TriadOutcome,
) -> VerdictDecision:
    """Translate a TriadOutcome into a single decision for the gateway.

    Rules:
      - UNANIMOUS or MAJORITY -> outcome.consensus.agreed_decision
      - SPLIT or INTEGRITY_FAILURE -> ESCALATE (always; no consensus =
        no decision; gateway escalates to human review).
    """
    if outcome.consensus.kind in (
        ConsensusKind.UNANIMOUS,
        ConsensusKind.MAJORITY,
    ):
        # agreed_decision is non-None for these two kinds by
        # construction in compute_consensus.
        return outcome.consensus.agreed_decision  # type: ignore[return-value]
    return VerdictDecision.ESCALATE
