# Verixa — SRE & Operations

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: SRE lead, on-call engineer, customer's operations team, procurement officer

---

## 1. Operational philosophy

Verixa runs against three operational philosophies:

1. **Production is sacred.** Verixa sits in the customer's regulated AI execution path. An outage doesn't just break a feature — it may stop the customer's regulated AI workflows entirely or, worse, leave them ungoverned. Operational discipline is non-negotiable.
2. **Audit-first observability.** The audit ledger is the source of truth for what happened. Operational telemetry (Prometheus, OpenTelemetry, structured logs) supplements the audit ledger; it does not replace it. Every operational metric must be reconcilable against the audit ledger.
3. **Customer-controlled when sovereign.** In Tier 1 and Tier 3 deployments, customer can see everything Verixa SREs see. No hidden telemetry, no out-of-band remote access without customer consent.

---

## 2. Service Level Objectives (SLOs)

Verixa publishes SLOs for the components most directly tied to customer business outcomes.

### 2.1 Runtime Gateway availability

- **Tier 4 (hosted SaaS):** 99.9% monthly availability
- **Tier 3 (sovereign managed):** 99.5% monthly availability (premium add-on: 99.95%)
- **Tier 2 (enterprise):** 99.5% Verixa application; customer infrastructure SLA applies
- **Tier 1 (on-prem):** 99.5% Verixa application; customer infrastructure SLA applies

### 2.2 Decision latency (low-risk path, no triad)

- **p50:** ≤ 25 ms
- **p95:** ≤ 40 ms
- **p99:** ≤ 50 ms

### 2.3 Decision latency (high-risk path, with triad)

- **p50:** ≤ 600 ms
- **p95:** ≤ 850 ms
- **p99:** ≤ 1000 ms

### 2.4 Audit emit completeness

- **100% of decisions** result in an audit ledger entry within 100 ms (async to hot path with strong durability guarantee)
- Zero data loss SLO on audit ledger; an audit emit failure is a critical incident

### 2.5 Replay availability

- **Hot tier:** replay query result returned within 30 seconds (p99)
- **Warm tier:** replay query result returned within 60 seconds (p99)
- **Cold tier:** replay query result returned within 24 hours

### 2.6 Compliance Dossier generation

- **Per-decision pack:** 5 minutes (p99)
- **Per-workflow pack (1 month range):** 1 hour (p99)
- **Annex IV dossier (3 month range):** 4 hours (p99)
- **Article 72 PMM pack:** 2 hours (p99)

### 2.7 Webhook delivery

- **First attempt:** within 5 seconds of event (p99)
- **Successful delivery:** 99.5% within 1 hour, 99.99% within 24 hours (with retry backoff)
- **Dead letter:** 24 hours after first attempt; customer alerted

---

## 3. Service Level Indicators (SLIs)

Each SLO is tracked by named SLIs published as Prometheus metrics:

```text
# Runtime Gateway availability
verixa_runtime_gateway_up{tenant_id="..."}
verixa_runtime_gateway_request_total{tenant_id="...", decision="..."}
verixa_runtime_gateway_request_failed_total{tenant_id="...", reason="..."}

# Decision latency
verixa_runtime_decision_latency_seconds_bucket{tenant_id="...", risk_class="..."}
verixa_runtime_decision_latency_seconds_count{tenant_id="..."}
verixa_runtime_decision_latency_seconds_sum{tenant_id="..."}

# Audit emit completeness
verixa_audit_emit_total{tenant_id="..."}
verixa_audit_emit_failed_total{tenant_id="..."}
verixa_audit_emit_latency_seconds{tenant_id="..."}

# Replay availability
verixa_replay_query_total{tenant_id="...", tier="..."}
verixa_replay_query_latency_seconds{tenant_id="...", tier="..."}

# Triad invocation
verixa_triad_invocations_total{tenant_id="...", consensus="..."}
verixa_triad_latency_seconds{tenant_id="..."}
verixa_triad_disagreements_total{tenant_id="..."}

# Webhook delivery
verixa_webhook_delivery_total{tenant_id="...", event_type="...", status="..."}
verixa_webhook_delivery_latency_seconds{tenant_id="...", event_type="..."}
verixa_webhook_dead_letter_total{tenant_id="...", event_type="..."}
```

These metrics are exposed via the Control Plane's `/v1/control/metrics` endpoint in Prometheus format. Customers in Tier 1 / 2 can scrape directly; Tier 3 / 4 customers see them in the Verixa Control Plane dashboard.

---

## 4. Observability stack

### 4.1 Metrics

- **Prometheus** for Verixa-internal metrics
- **OpenMetrics**-compatible exposition for customer scraping
- **Long-term metric storage** via Mimir / Thanos / customer's existing Prometheus infrastructure
- **Alerting** via Alertmanager → PagerDuty (Verixa SREs) + customer's on-call (Tier 3 / 4 with customer-side configuration)

### 4.2 Tracing

- **OpenTelemetry** for distributed traces
- Trace IDs propagate from customer's AI agent through Verixa Runtime Gateway, Policy Engine, Risk Engine, Triad Review, Audit Emit
- Customer's existing tracing backend (Jaeger / Tempo / Honeycomb / Datadog) consumes traces via OTLP

### 4.3 Logging

- **Structured JSON logs** at INFO level for normal operations, WARN/ERROR for actionable events
- **Log levels** controlled via environment configuration
- **Sensitive data redaction** at log emission; no PII or prompts in logs
- **Log forwarding** to customer SIEM via Fluentd / Vector / customer's preferred log shipper

### 4.4 Audit ledger as observability

The audit ledger is the highest-fidelity record of system behaviour. Operational dashboards query the audit ledger for:
- Governed actions/sec by workflow
- Decision distribution (allow/deny/escalate)
- Risk score distributions
- Triad consensus patterns
- Policy hit/miss patterns

This is queryable via the Control Plane API and visible in the Control Plane UI dashboards.

---

## 5. Incident response

### 5.1 Severity classification

- **S1 — Critical:** Verixa runtime down or fundamentally compromised; audit ledger integrity threatened; data exposure incident
- **S2 — High:** Significant degradation; SLO breach in progress; partial loss of capability (e.g. Triad reviewers unavailable, falling back to single-reviewer mode)
- **S3 — Medium:** Degraded but functioning; non-critical SLO breach; localised performance issue
- **S4 — Low:** Minor issue; no customer impact; tracked but not on-call escalated

### 5.2 Response SLAs (Tier 3 / 4 with 24/7 SRE)

| Severity | First response | Status update cadence | Resolution target |
|---|---|---|---|
| S1 | 15 minutes | Every 30 minutes | 4 hours |
| S2 | 30 minutes | Every 60 minutes | 12 hours |
| S3 | 4 hours | Daily | 5 business days |
| S4 | Next business day | Weekly | 30 days |

### 5.3 Customer notification

- **S1:** within 4 hours of incident detection
- **S2:** within 12 hours
- **S3:** within 48 hours
- **S4:** in monthly operational review

Customer notification includes: incident ID, severity, current state, customer impact assessment, mitigation in progress, ETA to resolution.

### 5.4 Post-incident review

Every S1 and S2 incident gets a post-incident review (PIR) within 5 business days. PIR includes:
- Timeline of events
- Root cause analysis
- Customer impact (governed actions affected, audit ledger integrity status, replay availability)
- Mitigation actions taken
- Preventive actions (engineering, operational, process)
- Customer-facing summary (shared with affected customers)

PIRs are published internally; customer-facing summaries are shared with affected customers and, on request, with their auditors.

---

## 6. Runbooks

Verixa publishes runbooks for the most common operational scenarios. Each runbook is versioned, tested, and reviewed quarterly.

### Runbook catalogue (Phase 1 baseline)

- **RB-001:** Runtime Gateway high error rate — diagnose, isolate, mitigate
- **RB-002:** Audit ledger emit lag — diagnose Postgres contention or Redis queue saturation
- **RB-003:** Triad reviewer model unavailable — fall back to two-of-three or single reviewer per policy
- **RB-004:** Postgres failover — primary down, promote replica
- **RB-005:** Object store unavailable — degraded snapshot capture; deferred replay
- **RB-006:** Vault unavailable — degraded; signing operations queued; alert customer
- **RB-007:** SPIFFE/SPIRE issue — service identity certificate issuance failure
- **RB-008:** OPA policy bundle failure — fall back to last-known-good bundle; alert
- **RB-009:** Webhook destination unreachable — backoff and dead letter
- **RB-010:** Customer IAM (OIDC) unreachable — degraded mode for Control Plane
- **RB-011:** MI300X capacity saturation — Triad scheduling backoff
- **RB-012:** Disk space exhaustion (Postgres / object store) — emergency capacity addition
- **RB-013:** Audit ledger integrity verification failure — incident response, forensic capture
- **RB-014:** Suspected security incident — IR procedures, customer notification, forensic capture
- **RB-015:** Policy bundle invalid Rego — block deployment, alert policy author
- **RB-016:** Retention tier mover failure — backlog accumulation handling
- **RB-017:** Replay job failure — diagnosis, retry, customer communication
- **RB-018:** Compliance Dossier generation failure — diagnosis, retry, regulator-deadline coordination

Phase 2+ adds runbooks as new modules ship (Approval Matrix Engine, Drift Monitor, Trust Graph, etc.).

---

## 7. Capacity management

### 7.1 Capacity dimensions

- **Compute (MI300X):** scaled by Triad invocation volume + reviewer model size
- **Postgres:** scaled by audit ledger growth rate + Trust Graph size
- **Object store:** scaled by replay vault snapshot size × retention duration
- **Redis:** scaled by rate-limit cardinality + OPA cache size
- **Network:** scaled by hot-path throughput + webhook fan-out

### 7.2 Capacity planning cadence

- **Monthly:** routine capacity review of Tier 3 / 4 deployments
- **Quarterly:** customer-level capacity review for Tier 2 / 3 customers
- **Per-pilot:** capacity sizing as part of pilot SOW
- **Annual:** infrastructure-wide capacity plan

### 7.3 Capacity alerts

- **Soft alert:** 70% of capacity in any dimension; SRE planning trigger
- **Hard alert:** 85% of capacity; immediate engineering response
- **Saturation:** 95% of capacity; emergency capacity addition

---

## 8. Backup and disaster recovery

### 8.1 Backup cadence

- **Postgres:** continuous WAL archiving + nightly base backup; 90 day retention in hot tier
- **Object store:** native object store durability (typically 99.999999999%); cross-region replication for Tier 3 / 4
- **Vault:** snapshot every 6 hours; encrypted backup retained 1 year
- **Configuration (Helm values, OPA bundles):** Git-backed; immutable history

### 8.2 DR testing

- **Annual full DR test** for Tier 3 / 4 deployments
- **Customer-led DR testing** supported and welcomed for Tier 1 / 2
- **Tabletop exercises** quarterly with engineering + SRE + customer success

### 8.3 RTO and RPO summary

| Component | RTO | RPO |
|---|---|---|
| Runtime Gateway | 30 seconds (active-active replicas) | N/A (stateless) |
| Postgres (audit ledger) | 30 seconds (Patroni failover) | 0 (synchronous replication) |
| Object store (Replay Vault) | 5 minutes | 1 minute |
| Vault | 30 minutes (failover to standby) | 6 hours (snapshot interval) |
| Reviewer models | 10 minutes (warm-up cost) | N/A (stateless) |
| Control Plane | 5 minutes | 5 minutes |

---

## 9. Change management

### 9.1 Change classes

- **Standard change:** routine patch deployment, configuration update; pre-approved per change class catalogue
- **Normal change:** new feature, schema migration, sector compliance pack release; CAB review
- **Emergency change:** critical security patch; expedited approval, post-deployment review

### 9.2 Deployment cadence

- **Patches and minor releases:** weekly to Tier 4 (hosted SaaS); bi-weekly to Tier 3 (sovereign managed); per-customer-window for Tier 1 / 2
- **Minor releases (feature additions):** monthly
- **Major releases (breaking changes):** every 6–12 months with 24-month support overlap on previous major

### 9.3 Customer notification of changes

- **Tier 4:** in-product changelog + email to designated technical contacts
- **Tier 3:** email + Customer Success engagement; deployment in customer-agreed window
- **Tier 2:** Customer-led deployment with Verixa support; release notes + upgrade runbook
- **Tier 1:** Same as Tier 2 plus on-site support window if requested

---

## 10. Operational metrics for customers

Customers see the following operational metrics in the Control Plane dashboard:

- **Governance volume:** governed actions/day, by workflow, by agent, by decision class
- **Risk profile:** risk score distribution, high-risk action volume, policy hit/miss
- **Triad utilisation:** triad invocations/day, consensus rates, disagreement rates
- **Human review:** queue depth, time-to-decision, reviewer utilisation
- **Audit and replay:** audit ledger growth, replay query volume, replay tier breakdown
- **Compliance dossiers:** dossiers generated/month, regulator-targeted dossiers
- **Operational health:** Verixa application availability, decision latency p50/p95/p99, audit emit lag
- **Trust Graph (Phase 4+):** workflow drift indicators, agent drift, supplier trust scores

---

## 11. Customer-facing operational artefacts

For Tier 2 / 3 / 4 customers:
- Monthly operational summary report
- Quarterly business review with Customer Success Lead
- Annual roadmap commitment review
- Continuous SLO tracking with customer-visible dashboard
- Incident reports for any S1 / S2 affecting the customer
- Capacity planning consultation as needed

For Tier 1 customers:
- Same as above plus on-site engineer rotation option
- Customer-controlled deployment windows
- Joint runbook reviews
- Quarterly architecture reviews

---

*This SRE & Operations document is the canonical operational reference for Verixa. The Security Architecture document specifies security operations; this document covers operational, capacity, and reliability practices. The Deployment Topology document specifies per-topology operational responsibilities. Updates require SRE Lead + Engineering Lead approval and quarterly review.*
