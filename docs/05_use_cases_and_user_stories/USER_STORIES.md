# Verixa — User Stories (companion to USE_CASES.md)

> User stories use the **job-stories** format ("When ___, I want to
> ___, so I can ___") rather than role-based ("As a ___, I want ___, so
> that ___"). Job stories capture *the situation that triggers the
> need*, which is more useful for prioritisation than the role of the
> person who happens to do it.

Each story maps to a use case in [`USE_CASES.md`](USE_CASES.md) and a
business requirement in [`../02_brd/BRD.md`](../02_brd/BRD.md).

---

## US-01 — See that a low-risk action was governed

**When** I am a security engineer reviewing yesterday's agent activity,
**I want to** see that low-risk read-only actions were validated against
policy before they ran,
**so I can** confirm the firewall + policy engine were active even on
non-escalated flows.

- **Maps to:** UC-01
- **Business requirement:** BR-01
- **Acceptance:** A `GET /v1/control/audit` query returns the low-risk
  entry with decision = `allow`, risk = `low`, `triad_invoked = false`,
  and a non-empty list of policy evaluations.

---

## US-02 — Trust that high-risk actions had independent review

**When** my organisation's AI is approving a non-trivial transfer,
**I want to** see three independent reviewers' verdicts + their pre-commit
hashes,
**so I can** demonstrate to my compliance team that the decision wasn't
made by a single model whose verdict could be retroactively rationalised.

- **Maps to:** UC-02
- **Business requirement:** BR-02
- **Acceptance:** The replay bundle for the decision contains exactly 3
  verdicts AND exactly 3 commitments, and `sha256(canonical_json(verdict)) ==
  commitment` for each reviewer.

---

## US-03 — See that a clearly bad action was stopped

**When** an AI agent tries to send USD 95,000 to an unverified beneficiary,
**I want to** see the action denied by policy *before* the expensive triad
review runs,
**so I can** demonstrate that the system fails fast and doesn't waste
compute on actions a policy alone can refuse.

- **Maps to:** UC-03
- **Business requirement:** BR-01, BR-07
- **Acceptance:** The audit entry shows `decision = deny`, `triad_invoked
  = false`, and ≥ 1 policy evaluation with `decision = fail`.

---

## US-04 — Onboard a new agent workflow without engineering help

**When** my security team wants to govern a new agent workflow,
**I want to** register it via a simple API (or UI) with name + sector + risk
threshold,
**so I can** start collecting evidence on day 1 without waiting on a
release.

- **Maps to:** UC-04
- **Business requirement:** BR-08
- **Acceptance:** `POST /v1/control/workflows` returns 201 with a
  workflow_id; that workflow_id is immediately queryable.

---

## US-05 — Tie audit entries to a specific agent identity

**When** I am investigating an incident and need to know *which* agent
caused it,
**I want** every audit entry to carry the agent's SPIFFE ID,
**so I can** trace activity to a specific deployed workload.

- **Maps to:** UC-05
- **Business requirement:** BR-08
- **Acceptance:** Every audit entry produced by an agent contains the
  agent's `spiffe_id` field.

---

## US-06 — Restrict a dangerous tool to one workflow

**When** I have a `transfer_funds` tool that should only ever be callable
from the Loan Approval Workflow,
**I want to** register it with `restrict_to_workflow = <loan-approval-id>`,
**so that** an agent in another workflow that tries to call it gets denied
by the firewall before policy runs.

- **Maps to:** UC-06
- **Business requirement:** BR-06
- **Acceptance:** A call to `transfer_funds` from a workflow not on the
  allow-list produces a `firewall_reject` audit entry.

---

## US-07 — Query the audit log by time window

**When** I am preparing a quarterly compliance report,
**I want to** pull every governed action in workflow X between Q1 start and
Q1 end,
**so I can** generate the report without manually grepping logs.

- **Maps to:** UC-07
- **Business requirement:** BR-01, BR-08
- **Acceptance:** `GET /v1/control/audit?workflow_id=&from=&to=` returns
  every entry whose timestamp falls in `[from, to)` and no others.

---

## US-08 — Reproduce a past decision in court-defensible form

**When** a regulator asks me to demonstrate *why* decision X was made,
**I want to** replay it and see the exact context the agent had at decision
time,
**so I can** show that the decision was made on the information available
then, not retrofitted.

- **Maps to:** UC-08
- **Business requirement:** BR-03
- **Acceptance:** `POST /v1/control/replay` returns a `ReplayBundle` whose
  `retrieved_documents` field matches what the agent saw at the timestamp
  of the original audit entry.

---

## US-09 — Generate a signed evidence pack on demand

**When** a customer's auditor asks for evidence of a specific decision,
**I want to** generate a portable signed JSON file in one API call,
**so I can** hand it over without exposing my live audit ledger.

- **Maps to:** UC-09
- **Business requirement:** BR-04
- **Acceptance:** `POST /v1/control/dossier` returns a `dossier_id`; the
  fetched dossier has `signature_hex` (128 hex chars) and `public_key_hex`
  (64 hex chars).

---

## US-10 — Verify a vendor's claims without trusting the vendor

**When** I receive a signed dossier from a Verixa customer,
**I want to** verify its signature using only the JSON + the public key + a
standard Ed25519 library,
**so I can** trust the evidence without trusting Verixa.

- **Maps to:** UC-10
- **Business requirement:** BR-04
- **Acceptance:** Running `tools/audit_verify.py <dossier.json>` on an
  air-gapped machine returns the same boolean result as running it online.

---

## Phase-1 stories (deferred)

| Story | Maps to | Why deferred |
|---|---|---|
| US-11 Approve an edge-case action manually | UC-11 | Needs SSO + role registry |
| US-12 Get warned about a contradictory new decision | UC-12 | Needs vector index of past decisions |
| US-13 Get a "this decision is suspicious" score | UC-13 | Needs ground-truth corpus per tenant |
| US-14 See agent behaviour drift over time | UC-14 | Needs longitudinal baseline |
| US-15 Trust another tenant's agent decisions | UC-15 | Needs federation primitives |

---

## Summary

**10 user stories** map 1:1 to UC-01 → UC-10, all backed by working
code and at least one test. **5 stories** are deferred to Phase 1+
with explicit reasons.

The companion files:
- [`USE_CASES.md`](USE_CASES.md) — the scenarios with mermaid sequence diagrams
- [`../02_brd/BRD.md`](../02_brd/BRD.md) — the business requirements these stories satisfy
- [`../17_traceability_matrix/TRACEABILITY_MATRIX.md`](../17_traceability_matrix/TRACEABILITY_MATRIX.md) — the BR → UC → US → Test mapping
