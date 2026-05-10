"""Verixa Triad Review Engine.

Three independent reviewer models inspect a candidate action and emit
verdicts. Verixa's contribution is the **hash-commit-and-reveal**
protocol that prevents reviewer collusion, post-hoc verdict tampering,
and "first-look bias" where a slow reviewer copies a fast one.

CP-10 sub-CPs:
  CP-10.1 -- pure protocol primitives (this commit): commit/reveal
              records, consensus algorithm, fixture types. No I/O.
  CP-10.2 -- reviewer client abstraction (OpenAI-compat HTTP wrapper).
  CP-10.3 -- triad orchestrator: parallel invoke + commit/reveal driver.
  CP-10.4 -- live MI300X integration test (gated by droplet up-check).
  CP-10.5 -- gateway integration: wire into R3-escalate path.

Protocol summary (full design in docs/04_security_and_audit
/SECURITY_AND_AUDIT.md A4 §6):

  Phase 1 (commit):
    - Each reviewer R_i computes verdict V_i and a fresh 256-bit
      nonce N_i (urandom).
    - Commitment: C_i = SHA-256(V_i_canonical || N_i).
    - All three commitments are published to the audit ledger
      BEFORE any reveal. This is the integrity anchor: once a
      commitment is on-chain, the verdict cannot be changed without
      breaking the SHA-256 binding.

  Phase 2 (reveal):
    - Each reviewer publishes (V_i, N_i).
    - Verifier checks SHA-256(V_i || N_i) == C_i for each i.
    - Any mismatch -> CONSENSUS_INTEGRITY_FAILURE; the action
      escalates and the reviewer is flagged.

  Phase 3 (consensus):
    - All three verdicts revealed and verified -> consensus rule:
        * 3 of 3 agree           -> UNANIMOUS    (full confidence)
        * 2 of 3 agree           -> MAJORITY     (acceptable for
                                                  ALLOW; reviewer-C
                                                  flagged for drift)
        * all three differ        -> SPLIT       (escalate to human;
                                                  no consensus)
    - "Agree" is computed on the verdict's `decision` field
      (allow/deny/escalate); free-text reasoning is preserved but
      not used for the consensus computation.

The protocol is **independent of the reviewer transport** -- vLLM,
HF Inference Endpoints, mock fixtures, all produce ReviewerVerdict
objects that flow through the same primitives.
"""

from verixa_runtime.triad.protocol import (  # noqa: F401
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


__all__ = [
    "Commitment",
    "ConsensusKind",
    "ConsensusOutcome",
    "ReviewerId",
    "ReviewerVerdict",
    "VerdictDecision",
    "canonicalise_verdict",
    "compute_commitment",
    "compute_consensus",
    "generate_nonce",
    "verify_reveal",
]
