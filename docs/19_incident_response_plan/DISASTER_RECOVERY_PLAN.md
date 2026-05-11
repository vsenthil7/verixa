# Verixa — Disaster Recovery Plan

> Companion to [`INCIDENT_RESPONSE_PLAN.md`](INCIDENT_RESPONSE_PLAN.md). The Incident Response Plan handles **operational** incidents (P0-P3 with defined response paths). This Disaster Recovery Plan handles **catastrophic** scenarios: total loss of a region, total loss of a primary system, or extended outage exceeding standard incident-response time-boxes. Aligned with **ISO 22301** Business Continuity and ISO 27031 ICT readiness.
>
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 baseline · Audience: SRE, Engineering Leadership, Risk Committee, customer's BCM team

---

## 1. Purpose

Disaster recovery answers a different question than incident response:

- **Incident Response** — "How do we restore service in minutes-to-hours?"
- **Disaster Recovery** — "How do we restore service when the normal restoration path is itself unavailable?"

The DR Plan exists because regulated buyers' business-continuity teams expect a specific ISO 22301 / ISO 27031 deliverable distinct from incident playbooks. Their auditors will ask for this document by name.

## 2. Scope

This plan covers:

- **Verixa-operated systems** (Tier 3 sovereign managed, Tier 4 hosted SaaS)
- **Customer-operated systems** (Tier 1 on-premises, Tier 2 private cloud) — Verixa supplies methodology + restoration tooling; customer operates the DR procedures

This plan does **not** cover:

- Customer's primary AI infrastructure (their DR responsibility)
- Customer's IdP / OIDC provider (their DR responsibility)
- Customer-managed key custody (their DR responsibility when customer-managed-key opted)

## 3. Recovery objectives

For each component Verixa operates, **RTO** (Recovery Time Objective — how fast we restore service) and **RPO** (Recovery Point Objective — how much data we can afford to lose). Tier 3 / Tier 4 defaults below.

| Component | RTO | RPO | Recovery strategy |
|---|---|---|---|
| Runtime Gateway | 15 minutes | 0 (stateless) | Re-route via load balancer to standby region |
| Control Plane API | 30 minutes | 0 (stateless) | Same as runtime gateway |
| Postgres (Audit Ledger + Registry) | 1 hour (Tier 3) / 30 min (Tier 4) | 5 minutes | Synchronous replication to standby; PITR backups |
| Replay Vault (MinIO/S3) | 30 minutes | 0 (cross-region replication) | Native object-store cross-region replication; content-addressable so corruption-detectable |
| OPA + policy bundle | 5 minutes | 0 (signed bundles in object store) | Stateless; restart with current signed bundles |
| Vault (key custody, Tier 3 / 4) | 30 minutes | 5 minutes | HA cluster across availability zones; per-tenant key escrow procedure for catastrophic loss |
| Triad reviewer infrastructure | 1 hour | N/A | Stateless model serving; standby capacity at second region; degraded-mode triad-on-CPU as last resort |

Total Service RTO (full end-to-end restoration): **2 hours** for Tier 3, **1 hour** for Tier 4 Pro.

## 4. Disaster scenarios

The DR Plan covers four categories of disaster. For each, we document the trigger, the response, and the test cadence.

### 4.1 Region loss

**Trigger:** total loss of the primary deployment region (cloud-provider regional outage, data-centre fire, natural disaster).

**Response:**
1. Page on-call SRE within 5 minutes of detection
2. Verify the region is truly unavailable (not a partial degradation that incident response handles)
3. **Failover decision** by SRE leadership: invoke region-failover or wait for restoration?
   - Region-failover invoked if expected restoration > RTO (2 hours Tier 3, 1 hour Tier 4 Pro)
4. Activate standby region:
   - Promote standby Postgres to primary
   - Point load balancer DNS to standby region
   - Trigger object-store failover (already replicated)
   - Activate standby Vault cluster
   - Restart Runtime Gateway + Control Plane API + Triad reviewers in standby
5. Verify with smoke test (the same smoke test that runs in CI per CP-21)
6. Notify customers per SLA notification commitments (§5 of `SLO_SLA_SPECIFICATION.md`)
7. Open public status-page incident

**Test cadence:** annual game-day exercise; tabletop quarterly.

**Owner:** SRE Lead

### 4.2 Primary system loss within a region

**Trigger:** total loss of a primary system (e.g. Postgres cluster cannot be restarted; Vault cluster lost; MinIO/S3 region-internal failure).

**Response:** restoration from backup OR failover to in-region standby. Specific procedures per system:

#### 4.2.1 Postgres total loss

1. Verify last successful PITR backup (continuous; no later than 5 min before incident)
2. Provision new Postgres cluster (Infrastructure-as-Code; ~10 min to running)
3. Restore from PITR backup to nearest valid point
4. Run audit-chain verification on restored data (`tools/audit_verify.py`); confirm integrity
5. Cut over Runtime Gateway + Control Plane API to new cluster
6. Monitor for hours after cutover

**Expected RTO:** 60 minutes (Tier 3) / 30 minutes (Tier 4)
**Expected RPO:** 5 minutes (last PITR backup point)

#### 4.2.2 Vault total loss with key recovery

This is the worst single-system loss because Vault holds the keys to everything sealed.

1. Page on-call SRE + page CTO
2. Verify Vault HA cluster lost (not a transient leader-election issue)
3. Recover from Vault's own Shamir-split unseal keys held in escrow (5-of-7 by default; held by separate Verixa officers per ISO 27001 separation-of-duties)
4. If Shamir recovery fails, escalate to **catastrophic-key-loss procedure** below

**Expected RTO:** 60 minutes (typical recovery) up to 24 hours (catastrophic-key-loss procedure)
**Expected RPO:** 0 (Vault is a key store, not a data store)

#### 4.2.3 Catastrophic key loss (Vault + escrow both lost)

A scenario where both the live Vault cluster AND the Shamir-split escrow are lost. This is the worst-case scenario for replay-bundle access.

The audit ledger remains readable (it isn't encrypted — it's signed). Replay bundles encrypted under per-tenant DEKs become **cryptographically unrecoverable**.

This is documented honestly. Customers' DPAs and the CSAFE attestation reference this scenario.

**Mitigations to prevent this:**

- Vault HA across 3+ availability zones in Tier 3 / 4
- Shamir-split unseal keys held by 7 individuals across 2+ geographic locations
- Quarterly drill of Shamir recovery (audit chain proves drills happened)
- Customer-managed-key option in Tier 1 / 2 / 3 puts the recovery responsibility with the customer (their existing key-management infrastructure)

**Response if it nonetheless occurs:**

1. Page CTO + CEO + DPO immediately
2. Audit ledger remains usable; replay bundles are not
3. Public disclosure within 24 hours
4. Customer-specific impact analysis: which tenants had data exclusively in unrecoverable replay bundles
5. Customer notification + offer of regenerated decisions (where customer can re-feed source data) OR contractual remediation
6. ICO / supervisory-authority notification per Article 33 if personal data involved

#### 4.2.4 Object store (MinIO/S3) total loss

Object stores are typically the most durable component (S3 = 11 nines). Total loss is rare but documented.

1. Verify cross-region replica is intact (cross-region replication is default Tier 3 / 4 posture)
2. Promote replica to primary
3. Point clients (Control Plane + Runtime) to promoted replica
4. Re-establish replication to a new third region

**Expected RTO:** 30 minutes
**Expected RPO:** 0 (replication is synchronous in Tier 4; near-sync 1-second window in Tier 3 cost-optimised)

### 4.3 Extended degraded performance

**Trigger:** sustained breach of latency SLO or error-rate SLO for > 24 hours despite incident-response remediation attempts.

This is not a system-loss disaster — it's a sustained operational problem. DR-class response is invoked when normal incident response cannot restore performance within 24 hours.

**Response:**

1. Engineering leadership convenes a tiger team
2. Customer-facing SLA reporting flags the sustained degradation
3. Service credits accrue per `SLO_SLA_SPECIFICATION.md` §5.6
4. Root-cause analysis runs in parallel to mitigation work
5. Architectural-change recommendation produced at end of incident

**Test cadence:** non-applicable (cannot drill); learned via real incidents.

### 4.4 Supplier collapse

**Trigger:** a sub-processor Verixa depends on collapses (e.g. cloud provider has region-wide outage extending beyond Verixa's contracted recovery time; SaaS supplier discontinues service).

**Response:**

1. Activate alternative supplier per pre-existing supplier-diversification strategy
2. Sub-processors with single-supplier dependency (per [`DATA_PROTECTION_AND_PRIVACY.md`](../13_data_protection_and_privacy/DATA_PROTECTION_AND_PRIVACY.md#8-sub-processor-management) §8) are documented; alternatives pre-identified
3. Customer notification per 30-day sub-processor-change clause OR emergency notification if change cannot wait 30 days

**Test cadence:** annual supplier-portfolio review; alternatives validated for restorability.

## 5. DR testing

ISO 22301 requires DR procedures to be exercised. Verixa's test cadence:

| Test type | Cadence | Scope | Owner |
|---|---|---|---|
| Tabletop exercise | Quarterly | Walk through DR scenarios as a team | SRE Lead |
| Postgres PITR restore drill | Quarterly | Restore last week's backup to a sandbox; verify chain | DBA Lead |
| Vault Shamir recovery drill | Quarterly | Recover Vault from escrow keys in sandbox | CTO + 5 key-holders |
| Object-store failover drill | Semi-annually | Promote replica in sandbox; verify reads | SRE Lead |
| Full region failover game-day | Annually | Standby region promoted; smoke tests pass; customer-impact-visible time measured | SRE Lead |
| Sub-processor alternative validation | Annually | Validate top-3 alternatives still work | Procurement + SRE |
| **External attestation** | Annually | Third-party verification of DR procedures (Tier 3 / 4) | Compliance |

Drill outcomes recorded in the audit ledger (every drill is an audit event); analysis fed into the Risk Register (§R-OPS-02 / R-OPS-03 likelihood scoring).

## 6. Communication during DR

### 6.1 Internal

- Incident commander assigned within 5 minutes of DR activation
- Stand-up cadence every 30 minutes during active recovery
- War-room channel established in incident-response tool
- Engineering leadership updated hourly

### 6.2 External

- Customer-impacting incident notification per SLA commitments (`SLO_SLA_SPECIFICATION.md` §5.1 / §5.2 / §5.3)
- Public status page updated within 15 minutes of DR activation
- ICO / supervisory authority notification: Verixa as Data Processor notifies the customer (Controller) within 24 hours of any personal-data-affecting DR event; customer is responsible for Article 33 supervisory notification

### 6.3 Post-DR retrospective

- Retrospective document delivered to affected customers within 7 calendar days
- Risk register updated with any new failure modes
- Incident-response runbook updated for any future similar incidents
- Engineering work-item created for any architectural change recommended by the retrospective

## 7. Governance

- **Plan owner:** SRE Lead
- **Plan reviewer:** CTO, DPO, Compliance, Risk Committee
- **Review cadence:** annual minimum; after every material drill; after every real DR event
- **Approval to invoke:** SRE Lead can invoke for §4.1 and §4.2; CTO required for §4.3 and §4.4 escalation

## 8. Compliance mapping

| Framework | Requirement | Where addressed |
|---|---|---|
| ISO 22301 | Business continuity management | This document end-to-end |
| ISO 27031 | ICT readiness for business continuity | §3 RTO/RPO + §4 scenarios + §5 testing |
| NIST SP 800-34 | Contingency planning for federal systems | §3 + §4 + §5 |
| EU NIS2 Directive Article 21 | Business continuity measures | §3 + §4 + §6 |
| UK Operational Resilience (FCA PS21/3, BoE SS1/21) | Impact tolerances | §3 RTOs + §5 testing |

For sector-specific frameworks (HIPAA Contingency Plan, PCI-DSS BCP, etc.), customer-specific addenda are negotiated per contract.

## 9. References

- ISO 22301:2019 Business continuity management systems
- ISO/IEC 27031:2011 ICT readiness for business continuity
- NIST SP 800-34 Rev. 1 Contingency Planning Guide for Federal Information Systems
- `docs/19_incident_response_plan/INCIDENT_RESPONSE_PLAN.md` — operational incidents (DR is for catastrophic failures only)
- `docs/18_sre_and_operations/SRE_AND_OPERATIONS.md` — day-to-day operational practices
- `docs/18_sre_and_operations/SLO_SLA_SPECIFICATION.md` — SLA commitments DR procedures must satisfy
- `docs/10_security_architecture/SECURITY_ARCHITECTURE.md` — security controls preserved during DR
- `docs/11_threat_model/RISK_REGISTER.md` — operational risks R-OPS-02 / R-OPS-03 / R-OPS-06 mitigated by this plan
- `docs/13_data_protection_and_privacy/DATA_PROTECTION_AND_PRIVACY.md` §14 — breach notification path
- `docs/07_system_architecture/adr/ADR-0006-postgres-audit-ledger-partitioning.md` — Postgres partitioning shapes Postgres DR
- `docs/07_system_architecture/adr/ADR-0008-vault-vs-cloud-kms-for-key-custody.md` — Vault / KMS choice shapes key-custody DR

---

*This Disaster Recovery Plan is the canonical reference for catastrophic-failure response. Day-to-day incidents follow the Incident Response Plan. SLA commitments DR must satisfy are in the SLO/SLA Specification. Risk treatments rely on this plan being current and tested.*
