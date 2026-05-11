# ADR-0003 — Commit-reveal protocol for triad consensus

- **Status:** Accepted
- **Date:** 2026-04-20
- **Phase:** 0 (hackathon prototype) — durable through Phase 1+
- **Decision owner:** v_sen
- **Affects:** Triad Review Engine, audit ledger (commitment fields), replay bundle schema

## Context

When three independent reviewers vote on a high-risk action, the **order of voting matters**. If Reviewer C sees Reviewer A's verdict before voting, C's vote is no longer independent — it's contaminated by anchoring or social proof, even if A and C are different LLM instances.

In a distributed-systems context, the classic mitigation is **commit-reveal**: each participant commits to a hash of their choice *before* any participant reveals their actual choice. Once all commits are recorded, participants reveal. Any participant who reveals a value whose hash doesn't match their earlier commitment is provably cheating.

Verixa's audit trail is **append-only and cryptographically signed**. We can leverage this to make the commit-reveal protocol *verifiable after the fact* by anyone with the dossier: the auditor can recompute `SHA-256(verdict)` and check it against the recorded commitment.

The naive alternative — "just call all three reviewers in parallel and merge the verdicts" — does not produce an audit trail that proves the reviewers couldn't see each other. It looks the same on the wire as a system where the reviewers DID see each other.

## Decision

For every triad invocation, run a **two-phase protocol**:

### Phase 1 — Commit

For each of the three reviewers:

1. Send the action envelope to the reviewer
2. Receive the reviewer's `Verdict` (decision + confidence + reasoning)
3. Compute `commitment = SHA-256(canonical_json(verdict))`
4. Record the commitment in the audit ledger **immediately**, before any verdict is recorded

Wait until all three commits are recorded before proceeding.

### Phase 2 — Reveal

For each of the three reviewers:

1. Record the reviewer's full verdict in the replay bundle
2. Compute `recomputed = SHA-256(canonical_json(verdict))`
3. Assert `recomputed == commitment` (recorded in Phase 1)
4. If the assertion fails, the reviewer is marked as **protocol-violating** and their verdict is excluded from consensus

### Consensus

Compute consensus across the three revealed verdicts using the configured rule (Verixa Phase 0 uses MAJORITY: 2 of 3 agreeing decisions wins). Record consensus outcome in the audit ledger.

### Canonical JSON

Use a strict canonical-JSON encoding for the verdict-to-bytes step: sorted keys, no insignificant whitespace, UTF-8, no trailing newline. This ensures that the same logical verdict always produces the same commitment, and that re-computing the commitment from the recorded verdict is deterministic on any platform. Implementation: `apps/runtime/verixa_runtime/triad/protocol.py::canonical_verdict_bytes()`.

Concrete files:

- `apps/runtime/verixa_runtime/triad/protocol.py` — `Verdict`, `Commitment`, `canonical_verdict_bytes`, `compute_commitment`, `verify_commitment_matches_verdict`
- `apps/runtime/verixa_runtime/triad/orchestrator.py` — drives Phase 1 then Phase 2; records both phases in the audit ledger
- Schema additions to `ReplayBundle.triad_review`: three `Verdict` objects + three `Commitment` objects, both lists ordered by reviewer identity

## Consequences

### Positive

- **Audit-verifiable independence.** An auditor reading the dossier can recompute the commitments and prove that the three verdicts existed *before* any reveal could have contaminated another.
- **Protocol-violating reviewers are caught.** If a reviewer is replaced mid-protocol (or its weights are modified between commit and reveal), the commitment check fails and the verdict is excluded.
- **Replay reconstructs the proof.** The dossier contains everything needed for offline verification — verdicts, commitments, the canonical-JSON spec, and the public key. No live call to Verixa is required.
- **Model-agnostic.** The protocol doesn't care if reviewers are LLMs, humans, or rule-based — it only cares that each produces a verdict and that the verdict is committed before revealed.

### Negative

- **Two round-trips per decision** instead of one. Latency roughly doubles. Acceptable because triad invocation is reserved for high-risk decisions (small fraction of total traffic).
- **Reviewers must support a "commit, then reveal" lifecycle.** In Verixa Phase 0 we sidestep this by having the orchestrator hold the verdict in memory between commit and reveal — the reviewer just emits a verdict once. The "commit" step is a hash *computed by the orchestrator on behalf of the reviewer*. This is a simplification we must document honestly.
- **Trust assumption: the orchestrator does not tamper with verdicts between commit and reveal.** If the orchestrator is compromised, the protocol provides no defence. Phase 1 will address this by having each reviewer compute its own commitment and send the commitment + verdict in separate signed messages.

### Mitigations

- The Phase-0 simplification is **clearly documented in the dossier**: the `triad_review.protocol_variant` field records `"orchestrator-computed-commitments-v0"` so any auditor knows the trust model.
- The protocol is **structurally ready** for Phase 1's reviewer-signed commitments — adding signatures is additive, not breaking. The dossier schema reserves a `reviewer_signature_hex` field that is currently empty.
- The audit ledger records commit and reveal as **separate entries** with their own timestamps, so even with orchestrator-computed commitments the temporal ordering is recorded.

## Alternatives considered

1. **No protocol — just parallel calls** — rejected. Audit trail can't distinguish independent parallel calls from sequential biased calls.
2. **Synchronous serial calls (A then B then C)** — rejected. Each reviewer sees the previous reviewers' verdicts; defeats the purpose.
3. **Encrypted verdicts revealed by key release** — considered. Strictly more secure but adds key-management complexity that isn't justified in Phase 0. The hash-commitment approach is the standard cryptographic primitive for this; encrypted-verdict variants are filed as a Phase-2 ADR candidate.
4. **Trusted execution environments (TEEs) for reviewers** — Phase 3+ direction. Eliminates the orchestrator-trust assumption entirely. Out of scope for now.

## Verification

- `packages/verixa-python/tests/test_triad_protocol.py` — unit tests for `compute_commitment`, `verify_commitment_matches_verdict`, canonical JSON determinism
- `packages/verixa-python/tests/test_triad_orchestrator.py` — orchestrator records commits before reveals; asserts ordering invariant; tests protocol-violating-reviewer detection
- `packages/verixa-python/tests/test_triad_integration.py` — gated live-MI300X tests assert that real reviewers produce verdicts whose recomputed commitments match (proves canonical JSON is deterministic across the wire)
- Demo seed decision B includes three commitments + three verdicts; the live HF Space smoke test (`_backup/smoke_test_hf_space.py`) asserts this end-to-end

## Related

- BRD: BR-02 (independent triad review)
- Use case: UC-02 (medium-risk transfer with triad consensus)
- Predecessor: ADR-0002 (reviewer choice)
- Phase 2 candidate: reviewer-signed commitments + per-reviewer keypairs
