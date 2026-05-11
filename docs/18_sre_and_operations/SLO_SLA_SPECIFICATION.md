# Verixa — Service Level Objectives (SLO) and Service Level Agreements (SLA)

> Companion to [`SRE_AND_OPERATIONS.md`](SRE_AND_OPERATIONS.md). The SRE doc describes *how* Verixa is operated; this document specifies *the measurable commitments* (SLIs, SLOs, SLAs) Verixa makes to customers per deployment tier.
>
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 baseline · Audience: Customer procurement, customer SRE, Verixa SRE, contracts team

---

## 1. Purpose

Customers under enterprise contract need committed performance levels they can take to their own customers, regulators, and audit bodies. This document specifies:

- **SLIs** (Service Level Indicators) — what gets measured
- **SLOs** (Service Level Objectives) — internal targets Verixa runs the system against
- **SLAs** (Service Level Agreements) — contractually-bound commitments, with credits for breach

The distinction matters: SLOs are Verixa's *internal* targets and may be higher than SLAs (engineering rule of thumb: run SLOs ~1 nine above SLAs to give error-budget headroom). SLAs are the customer-facing contract terms.

## 2. Tiered offering

Verixa offers four deployment tiers with different SLA postures.

| Tier | Topology | Availability SLA | Audience |
|---|---|---|---|
| **Tier 1 — On-premises** | Fully customer-operated | Customer-determined (Verixa supplies the SLO methodology) | Defence, intelligence, central banks, highly regulated public sector |
| **Tier 2 — Private cloud** | Customer cloud, Verixa-managed runtime | 99.5% | Financial services, healthcare, energy |
| **Tier 3 — Sovereign managed** | Verixa-operated, sovereign region | 99.9% | Regulated mid-market, pan-EU government |
| **Tier 4 — Hosted SaaS** | Verixa-operated, multi-tenant | 99.95% on Pro plan, 99.5% on Standard | Tech / digital-native enterprises |

The numbers below are Tier 3 + Tier 4 (Verixa-operated) defaults. Tier 1 / Tier 2 customers receive Verixa's SLO targets as guidance; their own SLAs are negotiated separately.

## 3. Service-Level Indicators (SLIs)

### 3.1 Runtime Gateway

| SLI | Measurement | Source |
|---|---|---|
| **Availability** | (successful HTTP 2xx + intentional 4xx) / (total) per minute | Front-edge load balancer + Prometheus |
| **Latency p50** | 50th-percentile time from request-in to decision-out | OpenTelemetry trace + Prometheus histogram |
| **Latency p99** | 99th-percentile time | same |
| **Error rate** | non-deliberate 5xx / total | same |
| **Throughput** | governed decisions per second | same |

### 3.2 Control Plane API

| SLI | Measurement |
|---|---|
| **Availability** | same shape as runtime |
| **Latency p99** | < 200ms for audit query; < 500ms for replay-bundle fetch; < 1s for dossier generate |
| **Error rate** | same |

### 3.3 Triad Review

| SLI | Measurement |
|---|---|
| **Availability** | triad-call success rate (denominator includes timeouts) |
| **Latency p99** | end-to-end triad (3 reviewer calls + consensus) |
| **Consensus integrity rate** | (consensus events where every reveal verified against commit) / total triad invocations |

### 3.4 Audit Ledger

| SLI | Measurement |
|---|---|
| **Durability** | (audit rows successfully verified at end-of-month against hash chain) / total |
| **Append latency p99** | time from `append()` call to row visible in query |
| **Verification correctness** | (chain-verification runs returning intact) / total runs |

### 3.5 Replay Vault

| SLI | Measurement |
|---|---|
| **Durability** | (replay bundles successfully decrypted at sample-time) / total sampled |
| **Snapshot latency p99** | time from `snapshot()` to bundle visible in store |
| **Replay latency p99** | time from `reconstruct(audit_id)` to bundle returned |

## 4. Service-Level Objectives (SLOs) — Tier 3 / Tier 4 Pro defaults

These are Verixa's **internal** targets. SLAs (§5) are typically one-nine looser.

| Component | SLI | SLO | Window |
|---|---|---|---|
| Runtime Gateway | Availability | 99.95% | 30-day rolling |
| Runtime Gateway | Latency p99 | < 300ms (excluding triad) | 30-day rolling |
| Runtime Gateway | Error rate (5xx) | < 0.05% | 30-day rolling |
| Control Plane API | Availability | 99.95% | 30-day rolling |
| Control Plane API | Audit query p99 | < 200ms | 30-day rolling |
| Control Plane API | Replay fetch p99 | < 500ms | 30-day rolling |
| Control Plane API | Dossier generate p99 | < 1s | 30-day rolling |
| Triad Review | Availability | 99.9% (one nine below others — model dependency) | 30-day rolling |
| Triad Review | Latency p99 | < 5s (3 sub-second reviewer calls + consensus) | 30-day rolling |
| Triad Review | Consensus integrity | 100.0% (zero tolerance — integrity failure escalates) | continuous |
| Audit Ledger | Durability | 100.0% (zero tolerance — verification must pass) | monthly review |
| Audit Ledger | Append latency p99 | < 50ms | 30-day rolling |
| Audit Ledger | Verification correctness | 100.0% | continuous |
| Replay Vault | Durability | 99.9999999% (9-nines target; equivalent to S3) | annual |
| Replay Vault | Snapshot latency p99 | < 200ms | 30-day rolling |
| Replay Vault | Replay latency p99 | < 1s | 30-day rolling |

### 4.1 Error budget

The error budget per SLO is the percentage of failures the SLO *permits*. For a 99.95% SLO over 30 days, the budget is 21.6 minutes.

When error budget burn exceeds 50% before the window's midpoint, change-freeze policy applies: only reliability / security work lands; feature work pauses until budget recovers.

When 100% of budget is burned, executive escalation triggers; post-mortem mandatory.

## 5. Service-Level Agreements (SLAs) — contractually bound

These are the customer-facing commitments. Loose by one nine compared with SLOs (per §4) to give engineering error-budget headroom.

### 5.1 Tier 4 Pro

| Commitment | Target |
|---|---|
| Runtime Gateway availability | **99.95%** (monthly, excluded incidents per §5.5) |
| Control Plane API availability | **99.95%** monthly |
| Audit Ledger durability | **100%** monthly (one verification failure within window triggers service credit) |
| Replay Vault durability | **99.999999%** annual (8-nines; matches S3 11-nines internally with headroom for SLA) |
| Customer-impacting incident notification | **within 15 minutes** of internal detection |
| Major-incident updates | **every 30 minutes** during incident |
| Post-incident retrospective delivery | **within 7 calendar days** of incident close |

### 5.2 Tier 4 Standard

| Commitment | Target |
|---|---|
| Runtime Gateway availability | **99.5%** monthly |
| Control Plane API availability | **99.5%** monthly |
| Audit Ledger durability | **100%** monthly |
| Customer-impacting incident notification | within 60 minutes |
| Major-incident updates | every 60 minutes during incident |

### 5.3 Tier 3 Sovereign managed

| Commitment | Target |
|---|---|
| Runtime Gateway availability | **99.9%** monthly |
| Control Plane API availability | **99.9%** monthly |
| Audit Ledger durability | **100%** monthly |
| Replay Vault durability | **99.999999%** annual |
| Customer-impacting incident notification | within 15 minutes |
| Compliance evidence-pack delivery (on-demand) | within **4 hours** of request |

### 5.4 Tier 1 / Tier 2

SLAs negotiated per customer; Verixa supplies the SLO methodology and engineering targets as input.

### 5.5 Excluded incidents

Time during the following events does not count against availability commitments:

- **Scheduled maintenance windows** (24-hour advance notice for routine; emergency security maintenance can shorten notice)
- **Customer-caused outages** (e.g. credentials revoked by customer's IdP)
- **Force majeure** (e.g. country-wide internet outage)
- **Customer's own primary AI provider outage** (the primary AI is upstream of Verixa)

Customer disputes around exclusions are resolved per the master agreement's dispute-resolution clause.

### 5.6 Service credits

Breach of an availability SLA triggers service credits:

| Actual availability (monthly) | Credit |
|---|---|
| 99.0% – SLA target | 10% of monthly fee |
| 95.0% – 99.0% | 25% of monthly fee |
| < 95.0% | 50% of monthly fee |

Service credits are the **sole and exclusive** remedy for availability SLA breach. Customer must request the credit within 30 days of the incident close.

## 6. Reporting

### 6.1 Customer-facing status

- Public status page at `status.verixa.dev` (Phase 1)
- Live SLI dashboards available to enterprise customers via Control Plane (Phase 1)
- Monthly SLA report emailed to named customer contact
- Quarterly executive summary including trend analysis

### 6.2 Internal SLO reporting

- Daily SRE stand-up reviews error-budget burn
- Weekly engineering leadership review reviews all SLO breaches
- Monthly executive review includes top-3 SLI risks
- Quarterly board reporting includes SLO trend + customer-impact summary

## 7. Change management for SLOs and SLAs

### 7.1 SLO changes

- Engineering proposes; SRE leadership approves
- Reviewed quarterly minimum
- Material loosening of an SLO triggers customer-success notification (no SLA change required since SLAs are looser)

### 7.2 SLA changes

- **Tightening** an SLA (more strict) → land on contract renewal; do not unilaterally tighten mid-contract
- **Loosening** an SLA → requires contract amendment and customer acceptance
- **Adding** a new SLA dimension → on next contract renewal

### 7.3 Methodology changes

This document's measurement methodology is bound by the master agreement. Material methodology changes (e.g. switching the availability formula from "successful HTTP 2xx + intentional 4xx / total" to a different formula) require contract amendment.

## 8. References

- Google SRE Book — Service Level Objectives chapter
- ISO/IEC 20000-1:2018 IT service management requirements
- ITIL 4 — service level management practice
- AWS Service Health Dashboard methodology (referenced for status-page design)
- `docs/18_sre_and_operations/SRE_AND_OPERATIONS.md` — operational practices implementing these SLOs
- `docs/19_incident_response_plan/INCIDENT_RESPONSE_PLAN.md` — incident response practices supporting SLA commitments
- `docs/19_incident_response_plan/DISASTER_RECOVERY_PLAN.md` — DR procedures supporting durability SLAs
- `docs/14_deployment_topology/DEPLOYMENT_TOPOLOGY.md` — tier definitions
- `docs/04_pricing_and_commercial/PRICING_AND_COMMERCIAL.md` — commercial terms tied to SLA tiers

---

*This document specifies SLO and SLA commitments. The contractual instrument that binds Verixa is the master agreement and its Service-Level Schedule, which references this document as the authoritative measurement methodology.*
