# Verixa — KPIs and Metrics Dashboard Specification

> Companion to [`SLO_SLA_SPECIFICATION.md`](SLO_SLA_SPECIFICATION.md). The SLO/SLA spec defines availability + latency + durability commitments. This document specifies the broader **business-and-product KPI** dashboard that Verixa operates against — what gets measured, how, who consumes it.
>
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 baseline · Audience: Engineering leadership, product, customer-success, finance, board

---

## 1. Purpose

SLOs/SLAs are technical commitments. KPIs answer broader business questions:

- Is the product delivering customer value?
- Is the product getting better over time?
- Is the business healthy?
- Where do we focus next?

This document specifies what the Verixa team measures, how the measurements are surfaced, and the cadence each dashboard is reviewed at.

## 2. KPI taxonomy

Five KPI dimensions. Per dimension: north-star metric, supporting metrics, dashboard, owner, review cadence.

### 2.1 Customer-facing performance

**North star:** customer SLA compliance rate (% of customers within all committed SLAs for the month)

**Supporting metrics:**
- Per-tier availability (rolled up from `SLO_SLA_SPECIFICATION.md` §4 SLIs)
- Per-tier latency p99
- Per-tier durability
- Per-customer SLA breach minutes (monthly)
- Customer-impacting incidents per month
- Customer-reported issues per month

**Dashboard:** SRE Tier-3 / Tier-4 monitoring + monthly customer-success report
**Owner:** SRE Lead
**Review cadence:** weekly SRE; monthly executive

### 2.2 Product effectiveness

**North star:** governed-decisions-per-customer per month (volume × adoption proxy)

**Supporting metrics:**
- Total governed decisions across all tenants
- Decisions per tenant per month
- DENY rate per tenant (what fraction of attempted actions get blocked)
- ESCALATE rate (triad invocation rate)
- ESCALATE-to-human rate (UC-11 invocation rate — Phase 1)
- Average risk score per tenant
- Audit-query rate per tenant
- Replay-reconstruction rate per tenant
- Dossier-generation rate per tenant
- Tool-firewall reject rate

**Dashboard:** Product analytics dashboard
**Owner:** Head of Product
**Review cadence:** weekly product team; monthly executive

### 2.3 Engineering velocity + quality

**North star:** deployment frequency × deployment failure rate (DORA-aligned)

**Supporting metrics (DORA):**
- Deployment frequency (deployments per week)
- Lead time for changes (commit to production)
- Change failure rate (% deployments that cause incident or require rollback)
- Mean time to restore (P0 incident open-to-close)

**Supporting metrics (Verixa-specific):**
- Test coverage (target 100% line+branch; current state: 1112 tests at 100%)
- Negative-test coverage rate (target Phase 1: 40%; current: ~36%)
- Ruff lint issues (target 0; current: 0)
- Open security vulnerabilities (target 0 critical; aged-by-priority graph)
- Open CFs (carry-forward items) trend
- Code-review wall-clock latency
- CI build time

**Dashboard:** Engineering dashboard
**Owner:** Engineering Lead
**Review cadence:** daily team stand-up; weekly engineering leadership

### 2.4 Compliance + governance

**North star:** % of governed decisions producing audit-grade evidence (target: 100%)

**Supporting metrics:**
- Audit-chain verification rate (target 100% monthly)
- Replay-reconstruction success rate (target 100% on sampled decisions)
- DPIA-completion rate among customers requiring DPIA
- Sub-processor SOC 2 / ISO refresh status (% in-date)
- Customer-driven data-subject-rights request handling SLA (target 100% within Article 12(3) 30-day)
- Personal data breach notifications (target 0; if > 0, severity by category)
- Regulatory finding count (open + closed)
- Penetration-test critical findings (open)
- CVE patching SLA compliance

**Dashboard:** Compliance dashboard
**Owner:** Compliance + DPO
**Review cadence:** monthly compliance team; quarterly risk committee

### 2.5 Business health

**North star:** monthly recurring revenue (MRR) growth rate

**Supporting metrics:**
- Active customers
- New customer acquisition (logos per quarter)
- Annual contract value (ACV) distribution
- Net revenue retention (NRR)
- Customer concentration (top-3 customer share of ARR)
- Gross margin
- Cash runway (months)
- Burn rate
- LTV / CAC (when meaningful — needs > 12 months data)
- Customer health score (per-customer composite of usage + satisfaction + commercial signals)

**Dashboard:** Finance + sales dashboard
**Owner:** CEO + CFO
**Review cadence:** monthly executive; quarterly board

## 3. Instrumentation

### 3.1 Data sources

| Source | Provides |
|---|---|
| Prometheus / Grafana | All SLIs from `SLO_SLA_SPECIFICATION.md` §3 |
| Audit ledger | Governed-decision counts, decision types, triad invocations |
| Replay vault | Replay-reconstruction counts, sample-based durability checks |
| Control Plane API | Operator activity, dossier generation, sub-processor health |
| Sentry / Datadog / OpenTelemetry | Errors, traces, performance distributions |
| GitHub + CI | Engineering velocity (DORA) |
| Vulnerability scanner (Trivy / Snyk) | CVE counts + age |
| Compliance tracker (Phase 1: Drata / Vanta) | Sub-processor refresh + control-evidence collection |
| CRM (HubSpot / Salesforce) | Customer-success + acquisition |
| Accounting (Xero / QuickBooks) | Financial KPIs |

### 3.2 Aggregation cadence

- **Real-time** for SLIs (seconds-level): availability, latency, error rate
- **5-minute roll-up** for product effectiveness (volume metrics)
- **Hourly** for engineering velocity (CI signal)
- **Daily** for compliance posture (CVE counts, control freshness)
- **Weekly** for business health
- **Monthly** for board reporting

### 3.3 Retention

- Real-time SLI data: 13 months (covers year-over-year analysis)
- Aggregate KPI data: 7 years (matches audit-ledger retention)
- Anonymised business analytics: indefinite (post-anonymisation no longer personal data)

## 4. Customer-facing analytics

A subset of KPIs is exposed to customers via the Control Plane (Phase 1):

- Their tenant's per-month governed decision count
- Their tenant's decision-type distribution
- Their tenant's triad invocation rate
- Their tenant's audit query count + replay count
- Their tenant's SLO compliance (per the public commitments)

Customers do not see cross-tenant aggregates. Verixa staff do not see customer-business-content (decision content) — only counts and outcomes.

## 5. Alerting

KPIs feed two alert classes:

- **SLO breach alerts** — operational; routed to on-call; per `SLO_SLA_SPECIFICATION.md` §4.1 error-budget rules
- **KPI drift alerts** — strategic; routed to engineering leadership / product / executives weekly; not real-time

Thresholds:
- Engineering velocity DORA metrics: alert if change failure rate > 15% over 4-week window
- Compliance: alert if any sub-processor SOC 2 falls out of date OR any CVE patching SLA missed
- Business: alert if cash runway < 12 months OR customer concentration > 60%

## 6. Governance

- KPI definitions reviewed quarterly by leadership; methodology change requires CFO/CTO co-sign
- Customer-facing analytics changes flow through change-management (CHANGE_MANAGEMENT_PROCESS.md normal-change category)
- Year-on-year KPI restatement: when methodology changes, prior-period KPIs restated for comparability

## 7. References

- Google SRE Book — Service Level Indicators chapter
- DORA — Accelerate: The Science of Lean Software and DevOps (Forsgren et al.)
- `docs/18_sre_and_operations/SLO_SLA_SPECIFICATION.md` — technical SLIs feeding §2.1
- `docs/18_sre_and_operations/SRE_AND_OPERATIONS.md` — operational practices producing the metrics
- `docs/04_pricing_and_commercial/PRICING_AND_COMMERCIAL.md` — pricing assumptions feeding business KPIs
- `docs/11_threat_model/RISK_REGISTER.md` — risks tracked via §2.4 metrics

---

*This KPI specification is the canonical reference for what Verixa measures. SLO/SLA technical commitments are in their dedicated document. Business KPIs feed board reporting per the cadence in §2.5.*
