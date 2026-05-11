# Verixa — Change Management Process

> Companion to [`SRE_AND_OPERATIONS.md`](SRE_AND_OPERATIONS.md). The SRE doc describes how Verixa runs operationally; this document describes how Verixa **changes** while running. Aligned with **ITIL 4 Change Enablement** practice and **ISO 20000-1 §8.5.1**.
>
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 baseline · Audience: SRE, Engineering, customer's change-management team, audit

---

## 1. Purpose

Buyers' change-management teams require a documented process for how Verixa introduces changes to production. Their auditors review this document during procurement. Verixa's commitment is that every production change follows a categorisation, an authorisation path, and a verification gate.

## 2. Change categories

ITIL 4 defines three change categories. Verixa adopts them with category-specific authorisation paths.

### 2.1 Standard change

**Definition:** pre-approved, low-risk, well-documented changes that follow a runbook.

**Examples:**
- Adding a tenant to the registry
- Rotating a routine API key per established procedure
- Deploying a code change that has passed all CI gates and exercises only pre-existing surfaces
- Routine OS / dependency patching within SLA window

**Authorisation:** pre-approved per category by Change Advisory Board (CAB); engineer executes without per-change approval.

**Lead time:** immediate.

**Verification:** automated tests + standard smoke tests post-deploy.

### 2.2 Normal change

**Definition:** medium-risk changes that require per-change review.

**Examples:**
- New feature deployment
- Schema migration
- Policy bundle replacement (signed)
- Sub-processor change
- SLA / pricing change

**Authorisation:** per-change CAB approval; minimum 1 engineering reviewer + 1 SRE reviewer; risk-owner consulted if change touches risk-registered system.

**Lead time:** target 5 business days; expedited path documented for time-pressed changes.

**Verification:** test coverage at 100% line+branch; relevant integration tests pass; post-deploy smoke test passes; SLO instrumentation in place; rollback procedure defined.

### 2.3 Emergency change

**Definition:** changes required immediately to address a P0 incident, security vulnerability, or imminent regulatory deadline.

**Examples:**
- Hotfix for active P0
- Critical security patch
- Time-bound regulatory disclosure response

**Authorisation:** SRE Lead + Engineering Lead can co-approve in real-time; CTO notified; CAB review post-hoc within 48 hours.

**Lead time:** as fast as the situation demands.

**Verification:** minimum viable test coverage; rollback plan; post-deploy verification; full retrospective within 7 days.

## 3. Authorisation workflow

```
Engineer drafts change → CI gates pass → 
  IF standard: deploy directly
  ELSE: CAB review (or emergency-approval pair) →
    Approved: deploy + verify
    Rejected: revise OR escalate
    Conditionally approved: address conditions then re-submit
```

CAB composition:
- **Standing members:** SRE Lead, Engineering Lead, Security Lead, Compliance Lead
- **Per-change consult:** risk owner if change touches risk-registered system; DPO if change touches personal-data flow; CFO if change has > £100K cost / revenue impact
- **Cadence:** twice-weekly for normal changes; on-demand for emergencies

## 4. Verification gates (every change)

Before any production deployment, all of:

| Gate | Standard | Normal | Emergency |
|---|---|---|---|
| CI test suite passes (pytest + vitest + Playwright) | ✓ | ✓ | minimum viable |
| Coverage at 100% line+branch | ✓ | ✓ | minimum viable |
| Ruff lint passes | ✓ | ✓ | minimum viable |
| Security scan (CVE) passes | ✓ | ✓ | risk-accepted with documentation |
| Smoke test in pre-prod | ✓ | ✓ | ✓ (cannot waive) |
| SLO instrumentation in place | n/a (already covered) | ✓ | ✓ |
| Rollback procedure documented | ✓ | ✓ | ✓ |
| Customer-impact analysis | n/a (no impact) | ✓ | post-hoc |
| Sub-processor / regulator notification if required | n/a | ✓ | post-hoc with mitigation |

## 5. Deployment

### 5.1 Production deployment policy

- **Blue/green** for Tier 3 / Tier 4 services where Phase 1 supports it; gradual cut-over with SLO monitoring
- **Canary** for high-risk changes; 5% → 25% → 100% with SLO gates
- **Synchronous rolling restart** for stateless services with health checks
- **Maintenance window** for changes requiring downtime; 24-hour advance customer notice (per `SLO_SLA_SPECIFICATION.md` §5.5)

### 5.2 Verification post-deploy

- Smoke test runs automatically post-deploy
- SLO dashboards monitored for 30 minutes post-deploy (extended to 4 hours for high-risk normal changes)
- Customer-facing status page updated if maintenance window was declared
- Audit ledger entry recorded for the deployment event

### 5.3 Rollback

- Every production deployment has a documented rollback procedure
- Rollback triggered if SLO breached in post-deploy monitoring window OR if customer-impacting issue surfaces within 24 hours
- Rollback decision: SRE Lead can call solo for SLO-driven rollback; CTO required for product-decision rollback

## 6. Documentation

### 6.1 Per-change record

Every change has a record in the change-management system (Phase 1) capturing:

- Change ID
- Category (standard / normal / emergency)
- Change description + risk classification
- Submitter
- CAB reviewers + decision
- Verification gates passed
- Deployment timestamp
- Post-deploy verification outcome
- Customer-impact notification (if applicable)
- Rollback (if invoked)

### 6.2 Audit trail

The change-management record itself is an audit-grade artefact. Retention: 7 years minimum.

## 7. Customer-facing notification

Per SLA commitments (`SLO_SLA_SPECIFICATION.md` §5):
- Standard changes: not customer-notified
- Normal changes: notified if customer-impacting; 24-hour advance for scheduled maintenance
- Emergency changes: notification within 30 minutes of execution for customer-impacting changes; post-hoc retrospective shared within 7 days
- Sub-processor changes: per DATA_PROTECTION_AND_PRIVACY.md §8.2 (30-day advance)

## 8. Compliance mapping

| Framework | Requirement | Where addressed |
|---|---|---|
| ITIL 4 | Change enablement practice | §2 categories + §3 authorisation |
| ISO 20000-1 §8.5.1 | Change management | §3 + §4 + §6 |
| ISO 27001 A.8.32 | Change management | §3 + §4 + §6 |
| ISO 27001 A.12.1.2 | Change management | §3 + §4 |
| NIST SP 800-53 CM-3 | Configuration change control | §3 + §4 |
| FCA SS21/3 (UK) | Change management for operational resilience | §3 + §4 + §5 |

## 9. References

- ITIL 4 Foundation — Change Enablement practice
- ISO/IEC 20000-1:2018 §8.5.1
- ISO/IEC 27001:2022 controls A.8.32 + A.12.1.2
- NIST SP 800-53 Rev. 5 CM-3 Configuration Change Control
- `docs/18_sre_and_operations/SRE_AND_OPERATIONS.md` — operational practices
- `docs/18_sre_and_operations/SLO_SLA_SPECIFICATION.md` — SLA commitments change management must satisfy
- `docs/19_incident_response_plan/INCIDENT_RESPONSE_PLAN.md` — emergency-change category aligns with P0 incident response
- `docs/11_threat_model/RISK_REGISTER.md` — risks reviewed when change touches registered system

---

*This Change Management Process is the canonical change-control reference. Day-to-day operational practices are in the SRE doc. SLA commitments tied to change are in the SLO/SLA Specification.*
