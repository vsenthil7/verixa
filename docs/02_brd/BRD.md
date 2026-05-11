# Verixa — Business Requirements Document (BRD)

> **Honest note on ordering.** This BRD was assembled at the end of
> Phase 0, *after* architecture and build. The canonical document
> chain is Vision → BRD → Use Cases → Architecture → Build → Tests.
> Phase 0 inverted that and back-filled this layer in CP-27.
> Phase 1 work will start from a real BRD-first cycle. The
> `17_traceability_matrix/` document records this discrepancy
> explicitly so the inversion isn't hidden.

---

## 1. Document control

| Field | Value |
|---|---|
| Title | Verixa Business Requirements Document |
| Phase | 0 (hackathon prototype) |
| Status | Issued, retrofit |
| Author | v_sen |
| Last revised | 2026-05-11 (CP-27) |
| Supersedes | none |

---

## 2. Business problem statement

Enterprises buying or building AI agents face a structural gap:
**no defensible audit trail** between an AI's decision and a real-world
action. Today the options are:

- Trust the agent vendor's logs — non-cryptographic, mutable, single source of truth
- Trust the agent's own self-report — circular, no independent verification
- Don't deploy AI agents to production — losing the value entirely

The forthcoming EU AI Act (high-risk system obligations, Articles
12–15), and existing financial-services / healthcare governance
regimes, already require audit, traceability, and human oversight.
None of the current AI agent stacks (LangChain, AutoGen, CrewAI, etc.)
produce evidence that **independently verifies** an action was governed
before it happened.

---

## 3. Strategic intent

Verixa is the runtime governance layer that sits *between* an AI agent
and the real world. Its job is to:

1. Intercept every action an agent attempts
2. Govern that action against signed policy
3. Verify high-risk actions via an independent reviewer triad
4. Record the entire decision context with cryptographic integrity
5. Produce evidence that an external auditor can verify **offline**, with
   no live dependency on Verixa

Verixa is intentionally **not** trying to replace the agent framework,
the LLM, or the compliance team. It produces the *evidence* those
teams need to do their jobs.

---

## 4. Target users (primary)

| User | Role | Pain | Willingness to pay |
|---|---|---|---|
| Platform security team | Owns AI runtime risk | Cannot prove governance happened | HIGH |
| Compliance / audit | Owns regulatory exposure | Cannot evidence Articles 12–15 of EU AI Act | HIGH |
| AI engineering lead | Owns agent deployments | Blocked by security/compliance review | MEDIUM |
| External auditor | Owns sign-off | Cannot verify vendor claims independently | INDIRECT (signal-driven) |

---

## 5. Business requirements (BR-NN)

Each requirement is **testable**, **traceable** (linked to use cases in
`05_use_cases_and_user_stories/`), and tied to a **success metric**.

### BR-01 — Every governed action produces tamper-evident evidence

**Requirement.** When an AI agent attempts an action through Verixa,
the resulting audit entry must be (a) append-only, (b) hash-chained
to its predecessor, and (c) signed with an Ed25519 key.

**Success metric.** 100% of governed actions produce an audit entry
whose signature verifies offline using a standard Ed25519 verifier.

**Traces to use cases.** UC-01, UC-02, UC-03, UC-07

### BR-02 — High-risk actions are reviewed by independent verifiers

**Requirement.** Actions exceeding a per-workflow risk threshold must
be reviewed by three independent reviewers (LLM or human). Each
reviewer must produce a verdict + a commitment hash *before* any
verdict is revealed (commit-reveal protocol). Consensus is computed
across the three.

**Success metric.** 100% of high-risk decisions show three commitments
+ three verdicts in their replay bundle, with the commitments matching
the SHA-256 of their respective verdicts.

**Traces to use cases.** UC-02

### BR-03 — Every decision is fully reconstructible after the fact

**Requirement.** For any past audit entry, an operator must be able to
reconstruct the full decision context: request envelope, retrieved
documents, tool I/O, policy evaluations, triad verdicts + commitments.
Replay is snapshot-based — what the agent saw at decision time — not
bit-exact regeneration.

**Success metric.** 100% of audit entries replay successfully on
demand, returning a `ReplayBundle` with no missing fields.

**Traces to use cases.** UC-08

### BR-04 — Compliance dossiers verify offline with no Verixa dependency

**Requirement.** A signed compliance dossier must contain everything
an external auditor needs to verify (a) the audit entry's authenticity
and (b) the decision trail's integrity, *without* a live call to
Verixa. Verification uses only the JSON payload, the Ed25519 signature,
and the published public key.

**Success metric.** A dossier verified on a fully air-gapped machine
using a standard Ed25519 library produces the same boolean result as
a verification done online.

**Traces to use cases.** UC-09, UC-10

### BR-05 — Per-tenant cryptographic isolation enables Article 17 erasure

**Requirement.** Replay bundles must be encrypted with per-tenant
AES-256-GCM keys. Destroying the per-tenant key must render every
replay bundle for that tenant cryptographically unreadable. This
provides a defensible Article 17 (GDPR right to erasure) mechanism
that doesn't require physically deleting every audit row.

**Success metric.** After a per-tenant key is zeroised, any attempt
to decrypt that tenant's replay bundles fails with `InvalidTag`.

**Traces to use cases.** Phase-1 (UC-11+); enabling infrastructure
exists in Phase 0.

### BR-06 — Tool calls are filtered through an allow-list + arg bounds

**Requirement.** Tools must be registered with explicit argument
schemas and bounds. A call that exceeds bounds or names an
unregistered tool is denied *before* any other governance check
runs (fail-fast).

**Success metric.** 100% of unregistered tool calls are denied with
a `firewall_reject` audit entry.

**Traces to use cases.** UC-06

### BR-07 — Policy bundles are signed and cacheable

**Requirement.** Policy bundles must be signed by an authorised
signing key. Bundles can be cached locally for performance, but
the gateway must refuse to evaluate against a bundle whose
signature does not verify.

**Success metric.** An unsigned or tampered bundle is rejected at
gateway start-up; no evaluation runs against it.

**Traces to use cases.** (cross-cutting; underlies UC-02 and UC-03)

### BR-08 — Operator surface (Control Plane API + UI) for human review

**Requirement.** Platform operators need a programmatic API and a
visual interface to: register workflows / agents / tools, query the
audit ledger, replay decisions, and generate dossiers on demand.

**Success metric.** Every API endpoint has a corresponding UI page
that exercises it; every page passes a Playwright happy-path and
error-path test.

**Traces to use cases.** UC-04, UC-05, UC-06, UC-07, UC-08, UC-09

---

## 6. Non-functional requirements (NFR-NN)

These derive from `06_regulatory_mapping/` and the threat model.

### NFR-01 — Audit ledger is append-only

No mutation paths exist. All writes go through the hash-chain emitter.

### NFR-02 — All cryptographic operations use standard primitives

Ed25519 (signing), AES-256-GCM (sealing), SHA-256 (hash chain). No
custom crypto. **Implemented via `pynacl` + `cryptography`.**

### NFR-03 — System runs on a single container in Phase 0

In-memory `Protocol`-typed stores. Phase 1 swaps to Postgres + MinIO
without API or UI changes.

### NFR-04 — 100% test coverage on hot-path code

Line + branch coverage on every module in `apps/runtime/`,
`apps/control-plane-api/`, and `packages/verixa-python/`. Enforced
by `fail_under = 100` in `pyproject.toml`.

### NFR-05 — Compliance language discipline

Source code, commit messages, README, dossiers, and submission
material must use hardened compliance language: "every governed
action" not "every action"; "Annex IV-aligned" not "regulator-ready";
"evidence supports demonstrating" not "proves". Enforced via review
discipline; the `20_glossary/` is the single source of truth.

### NFR-06 — Live demo must work in 30 seconds with zero setup

Container boots pre-seeded so a hackathon judge or buyer can click
through every flow on the first visit without registering data first.

---

## 7. Out of scope for Phase 0

Documented to scope the conversation, not because the work isn't
valuable:

| Scope-out | Why deferred |
|---|---|
| Persistent storage (Postgres, MinIO) | Phase 0 ships in-memory; protocol interfaces ready for Phase 1 |
| SPIFFE / SPIRE workload attestation | Phase 0 records SPIFFE ID but doesn't attest it |
| HashiCorp Vault / KMS-backed signing keys | Phase 0 mints an Ed25519 keypair at container start |
| Multi-tenancy beyond cryptographic isolation | Phase 0 has the AES-key infrastructure but no tenant registry UI |
| Approval matrix (human-in-the-loop) | Phase 1 — needs SSO + role registry |
| Contradiction / hallucination scoring | Phase 2 — needs vector index + ground-truth corpus |
| Trust graph / federation | Phase 4 — needs cross-tenant primitives |

---

## 8. Acceptance criteria for Phase 0 sign-off

This BRD is satisfied for Phase 0 when:

1. ✅ BR-01: every audit entry verifies offline (proven by `test_audit_verifier.py`)
2. ✅ BR-02: triad commit-reveal protocol works (proven by `test_triad_orchestrator.py` + 4 gated MI300X tests)
3. ✅ BR-03: replay reconstructs decisions (proven by `test_replay_snapshotter.py`)
4. ✅ BR-04: dossiers verify offline (proven by `test_dossier_manifest.py` + `tools/audit_verify.py`)
5. ✅ BR-05: cryptographic erasure works (proven by `test_replay_sealer.py`)
6. ✅ BR-06: firewall blocks unregistered tool calls (proven by `test_firewall_allowlist.py`)
7. ✅ BR-07: policy bundles must verify (proven by `test_policy_signing.py`)
8. ✅ BR-08: Control Plane API + UI exist (proven by 1108 tests + live HF Space)

**All 8 acceptance criteria met as of 2026-05-11.**

---

## 9. Traceability

See [`17_traceability_matrix/TRACEABILITY_MATRIX.md`](../17_traceability_matrix/TRACEABILITY_MATRIX.md)
for the BR → UC → Test → Implementation file mapping.
