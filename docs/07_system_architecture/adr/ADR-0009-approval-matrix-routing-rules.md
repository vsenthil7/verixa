# ADR-0009 — Approval-matrix (human-in-the-loop) routing rules

- **Status:** Proposed (Phase 1 placeholder)
- **Date:** 2026-05-11
- **Phase:** 1 (production rollout)
- **Decision owner:** TBD at Phase 1 kickoff
- **Affects:** UC-11 escalation flows, operator queue UI, approver role registry, decision-latency SLO

## Context

Phase 0 implements the triad escalation path (CP-10): when the firewall + policy + risk path produces an ESCALATE decision, the triad of three reviewers reaches a verdict via commit-reveal protocol. Phase 0's triad is three Qwen3-0.6B instances; final verdict is automated.

Phase 1 adds **human-in-the-loop approval** (UC-11). When the triad itself escalates (consensus = SPLIT or INTEGRITY_FAILURE), or when policy explicitly requires human approval (e.g. transfers above £1M), the decision routes to a human approver queue. The approval matrix defines:

- **Who can approve what** — role × workflow × risk-bucket → approver-role mapping
- **Quorum requirements** — single-approver / dual-approver / committee
- **SLA** — how long an approval can sit before timing out
- **Timeout behaviour** — auto-deny / auto-escalate / auto-allow-with-flag
- **Audit requirements** — approver identity + rationale captured in the audit ledger

A second design question: **the operator UI surface**. Approvers need a queue view, a decision-detail view, action buttons (Approve / Deny / Request More Info), and a rationale-capture textarea.

## Decision (preliminary lean)

**Three-layer approval model:**

1. **Policy-defined approval requirements.** Rego policies declare per-workflow: "transfers > £1M require Senior-Reviewer approval; transfers > £10M require dual Senior + Compliance approval." This is data, not code; lives alongside other Phase 0 policies in `policies/<tenant>/<workflow>.rego`.

2. **Approver role registry.** Each tenant declares its approvers + roles + delegation chains in a per-tenant table. Roles are tenant-scoped; one global "VerixaSeniorReviewer" role does not exist.

3. **Quorum engine.** When a decision needs N approvals, the engine routes to N approvers (or 1 with delegation chain), tracks their responses, applies the timeout, and emits the final decision back to the runtime gateway.

**SLA defaults:**
- Auto-timeout: 4 hours business-hours / 12 hours always-on (tenant configurable)
- Timeout behaviour: auto-escalate to next approval tier; final tier timeout = auto-deny + alert
- Approver rationale: required free-text field, captured in audit ledger verbatim

**Queue UI** lives in the Control Plane Next.js app at `/approvals` (new Phase 1 route) with: queue list filtered by approver role, decision detail with full envelope + triad verdict, Approve / Deny / Request More Info action buttons with rationale textarea.

Final decision deferred to Phase 1 kickoff after Phase 1 design-partner customers describe their existing approval matrices (most regulated buyers have these documented for non-AI processes).

## Consequences

### Positive

- **Policy-as-data approval rules** mean customers can change their approval matrix without code changes; Rego diffs land via the policy bundle distribution path (Phase 1 OPA infra work).
- **Per-tenant role registry** avoids one-size-fits-all; a fintech and a healthcare customer have very different role taxonomies.
- **Audit-ready by construction.** Every approval action is an audit event; approver rationale is mandatory; quorum requirements are policy-visible.
- **The Phase 0 triad escalation path already exists** — quorum-engine work is additive, not a rewrite.

### Negative

- **The approval queue UI is non-trivial** — must handle bulk operations, search, delegation overrides, out-of-office routing. Phase 1 scope must bound this.
- **Latency goes up.** A decision waiting for human approval has zero p99 latency bound in the way agent decisions do.
- **Approver fatigue** — too-frequent approval requests get rubber-stamped. Phase 1 must instrument approval-rate-per-approver-per-day and alert on fatigue.
- **Delegation chains** introduce complexity. A → B → C delegation must record who actually approved, not just who was nominally responsible.

### Mitigations

- Phase 1 UI scope: queue + detail + action + rationale + simple approver-search. Bulk operations, advanced search, custom views = Phase 2.
- Default approval SLAs are tenant-configurable and visible in operator dashboards.
- Approver fatigue metrics surface in the operator KPI dashboard (separate Phase-1 work, post-this-ADR).
- Delegation chain logs who-acted-on-behalf-of-whom; audit ledger records actual approver, not nominal.

## Alternatives considered

1. **Single-tier "human approval needed: yes/no" flag.** Rejected. Regulated customers have multi-tier approval matrices; one flag is not enough.
2. **Hard-code approval matrix in Verixa code.** Rejected. Customers' approval matrices are theirs; Verixa providing them is policy-by-vendor, which fails audit.
3. **External approval system integration only** (Verixa hands off to ServiceNow / Jira / etc.). Considered. Likely a Phase-2 addition: integrate with external systems for customers who already operate them. Phase 1 needs an in-house path because not all customers have a ticketing system that fits.
4. **Real-time chat-based approvals (Slack / Teams).** Considered. Phase 2 integration. Real-time chat approvals are convenient but break audit-trail discipline (chat messages can be deleted; audit logs cannot).

## Verification

- Phase 1 must demonstrate UC-11 end-to-end with at least one design-partner customer's real approval matrix.
- Approval SLA must be configurable per tenant + per workflow.
- Audit log must reconstruct "for this decision, who approved, when, with what rationale, after how many minutes".
- The Phase 0 triad escalation must continue to work — UC-11 is additive, not replacing.

## Related

- UC-11 (human-in-the-loop approval) in `docs/05_use_cases_and_user_stories/USE_CASES.md`
- BR-03 (decision replay) — approver actions are replay-visible
- BR-08 (operator surface)
- ADR-0001 (in-memory stores) — the approver role registry becomes a Phase-1 Postgres table
- ADR-0007 (auth) — approvers authenticate via operator API keys
- Phase 0 triad escalation in `apps/runtime/verixa_runtime/triad/orchestrator.py` — quorum engine is the human-tier extension of this
