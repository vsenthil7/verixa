# Verixa — Risk Register

> Companion to [`THREAT_MODEL.md`](THREAT_MODEL.md). The threat model identifies adversarial scenarios; this register tracks the enterprise risks that flow from those scenarios plus other categories (operational, compliance, financial, strategic, reputational) and applies **ISO 31000 / ISO 31010** risk-management methodology.
>
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 baseline · Audience: Verixa risk committee, customer's third-party risk team, audit committee, board

---

## 1. Purpose

This Risk Register is the canonical inventory of risks Verixa faces or causes. It exists separately from the Threat Model because:

- **Threat Model** answers "what adversaries could do" — STRIDE / kill-chain / attack-tree framing
- **Risk Register** answers "what could go wrong for the business" — ISO 31000 framing including non-adversarial risks (operational failures, regulatory change, supplier risk, market risk, strategic risk)

The two cross-reference each other: every threat in the Threat Model maps to one or more risk entries here; risk entries that originate in adversarial scenarios point back to the threat model entry that drives them.

A buyer-side third-party risk assessment, a customer's enterprise risk committee, and an internal audit body all consume this register. The Threat Model is for security teams.

## 2. Risk taxonomy

Verixa categorises risks across six dimensions (ISO 31000 §6.4):

| Category | Examples |
|---|---|
| **Strategic** | Market direction wrong; competitor leapfrogs; product-market fit erosion |
| **Operational** | Service outage; data loss; key person dependency; supplier failure |
| **Compliance** | Regulatory change; lawful basis challenge; cross-border transfer ruling; audit finding |
| **Security** | Adversarial attack succeeding; vulnerability exploitation; insider threat |
| **Financial** | Cash runway; foreign exchange; customer concentration; pricing model misfit |
| **Reputational** | Public incident; customer relationship damage; press coverage; social media |

## 3. Risk-scoring methodology

Each risk is scored on **likelihood × impact**, producing a heat-map position. Verixa uses 5×5 (more granular than the 3×3 in the DPIA template — different audience).

**Likelihood (1–5):**

| Level | Meaning | Annual probability |
|---|---|---|
| 1 — Rare | May occur in exceptional circumstances | < 5% |
| 2 — Unlikely | Could occur but not expected | 5–20% |
| 3 — Possible | Might occur in some circumstances | 20–50% |
| 4 — Likely | Will probably occur in most circumstances | 50–80% |
| 5 — Almost certain | Expected to occur | > 80% |

**Impact (1–5):**

| Level | Operational | Financial | Reputational | Compliance |
|---|---|---|---|---|
| 1 — Insignificant | < 1 hour service interruption; routine | < £10K | Internal only | Routine finding |
| 2 — Minor | 1–8 hours; one tenant | £10K–£100K | One customer impacted | Minor non-conformance |
| 3 — Moderate | 8–48 hours; multiple tenants | £100K–£1M | Trade press coverage | Material non-conformance; remediation required |
| 4 — Major | > 48 hours; broad customer impact | £1M–£10M | National press coverage | Enforcement action; significant fine |
| 5 — Catastrophic | Multi-day outage; data loss; customer flight | > £10M; or contract termination | Front-page; reputational damage | Regulatory consent order; criminal exposure |

**Risk score = likelihood × impact** (range 1–25).

**Treatment thresholds:**
- 1–4 → **Tolerate** with documented rationale and monitoring
- 5–9 → **Treat** — mitigations land in current planning cycle
- 10–14 → **Treat urgently** — mitigations land in current quarter; report to risk committee
- 15–25 → **Avoid** — block deployment / cease activity until residual ≤ 9 OR escalate to board with documented acceptance

## 4. Register

| # | Category | Risk description | Likelihood | Impact | Score | Treatment | Owner | Review cadence |
|---|---|---|---|---|---|---|---|---|
| **R-STR-01** | Strategic | Frontier-LLM provider releases native governance feature that subsumes Verixa value proposition | 3 | 4 | 12 | **Treat urgently:** maintain heterogeneous-triad differentiation (ADR-0002, future ADR-0011); deepen evidence-pack uniqueness; lock-in via compliance pack moats (Phase 5) | CEO | Quarterly |
| **R-STR-02** | Strategic | Regulatory landscape consolidates around a single mandated governance standard Verixa doesn't fit | 2 | 5 | 10 | **Treat urgently:** active participation in standards bodies (NIST AI RMF, ISO 42001, EU AI Act WG); modular architecture allows new framework adapters | CTO | Quarterly |
| **R-STR-03** | Strategic | Sovereign-cloud thesis weakens (e.g. Schrems III resolves, US-EU adequacy stabilises) | 2 | 3 | 6 | **Treat:** product also works in hyperscaler cloud (Tier 4); sovereign positioning is differentiator not sole offering | CEO | Annual |
| **R-OPS-01** | Operational | HF Spaces (demo) becomes unavailable or changes free-tier policy | 4 | 1 | 4 | **Tolerate:** demo can be rehosted on AMD Developer Cloud in < 1 day; not on revenue path | CTO | Annual |
| **R-OPS-02** | Operational | Postgres data loss in production tier (Phase 1+) | 2 | 5 | 10 | **Treat urgently:** Postgres HA + synchronous replication + PITR backups + quarterly restore drills; documented in DR Plan | SRE Lead | Quarterly |
| **R-OPS-03** | Operational | Replay Vault MinIO/S3 corruption | 2 | 5 | 10 | **Treat urgently:** content-addressable storage + Ed25519 anchor chain catches corruption; cross-region replication for Tier 3/4 | SRE Lead | Quarterly |
| **R-OPS-04** | Operational | Single-person dependency on Phase-0 codebase (v_sen sole author) | 5 | 4 | 20 | **Treat urgently:** docs hardening (CP-25 → CP-30) lowers this; Phase 1 hires reduce further; ADRs preserve decision context | CEO | Continuous |
| **R-OPS-05** | Operational | MI300X live demo dependency on AMD-side availability | 3 | 1 | 3 | **Tolerate:** demo gracefully degrades to mock triad if live endpoint down; documented in README | CTO | Annual |
| **R-OPS-06** | Operational | Sub-processor failure (Vault, Postgres provider, IdP) | 2 | 4 | 8 | **Treat:** multi-provider strategy for cloud topologies; Vault failover documented in DR Plan; sub-processor SOC 2 review annually | SRE Lead | Annual |
| **R-COM-01** | Compliance | UK or EU AI Act interpretation evolves such that Verixa's evidence pack becomes insufficient | 3 | 4 | 12 | **Treat urgently:** active monitoring of EDPB, ICO, EU AI Office, national supervisors; modular evidence pack allows additional fields without breaking change | DPO + Compliance | Quarterly |
| **R-COM-02** | Compliance | Customer's Article 35 DPIA flags Verixa as unacceptable residual risk | 2 | 4 | 8 | **Treat:** DPIA template (DPIA_TEMPLATE.md) supports customer; sovereign topology (Tier 1/3) addresses common residual risks; willing to engage with customer DPO | DPO | Per onboarding |
| **R-COM-03** | Compliance | Cross-border transfer mechanism invalidated (Schrems-III class) | 2 | 3 | 6 | **Treat:** Tier 1 + Tier 3 sovereign topologies avoid transfer entirely; SCCs + DPF backup for cloud topologies | DPO | Continuous |
| **R-COM-04** | Compliance | Audit ledger 7-year retention found insufficient by sector regulator | 2 | 3 | 6 | **Treat:** configurable retention per tenant; sector compliance packs (Phase 5) extend default to 10 / 15 years as required | Compliance | Annual |
| **R-SEC-01** | Security | Reviewer-triad collusion attack (Threat Model T-3.2) | 2 | 5 | 10 | **Treat urgently:** Phase 2 heterogeneous models (Qwen3-72B + Llama-3.3-70B + DeepSeek-V3) per ADR-0011-future; commit-reveal protocol per ADR-0003 prevents in-flight collusion | CTO | Per release |
| **R-SEC-02** | Security | Audit-ledger tampering attack (Threat Model T-2.1) | 1 | 5 | 5 | **Treat:** Ed25519 chain + standalone offline verifier + Phase 1 Postgres partitioning preserves chain (ADR-0006) | CTO | Per release |
| **R-SEC-03** | Security | Per-tenant DEK compromise reveals tenant data | 1 | 5 | 5 | **Treat:** key-custody via Vault/KMS per ADR-0008; customer-managed-key option in Tier 1/2/3; cryptographic erasure available on revocation | CTO | Per release |
| **R-SEC-04** | Security | Verixa container image supply-chain attack | 2 | 4 | 8 | **Treat:** Cosign-signed images Phase 1; SLSA-Level-3 build pipeline target Phase 2; CycloneDX SBOM (Phase 2 ADR-future) | CTO | Continuous |
| **R-SEC-05** | Security | Verixa staff insider threat in Tier 4 multi-tenant | 2 | 4 | 8 | **Treat:** per-tenant key hierarchy prevents Verixa-staff decryption; principle of least privilege; audit log of every staff action | CTO + CEO | Annual |
| **R-FIN-01** | Financial | Customer concentration: first 3 customers > 60% of ARR | 4 | 4 | 16 | **Avoid / Treat urgently:** active diversification target by month 12 post-Phase-1; documented in board pack | CEO | Quarterly |
| **R-FIN-02** | Financial | Cash runway falls below 12 months | 3 | 5 | 15 | **Avoid / Treat urgently:** quarterly runway review; fundraising trigger at 12 months; contingency plan at 9 months; revenue-vs-burn dashboard | CFO / CEO | Monthly |
| **R-FIN-03** | Financial | Foreign exchange exposure on UK/EU/US split | 3 | 2 | 6 | **Treat:** invoice in customer's home currency where commercially viable; hedging review when > £5M cross-currency exposure | CFO | Quarterly |
| **R-FIN-04** | Financial | Long sales cycle in enterprise compliance causes deferred revenue mismatch | 4 | 3 | 12 | **Treat urgently:** mid-market entry-tier offering to accelerate cash; design-partner pricing with fixed milestone payments | CRO | Quarterly |
| **R-REP-01** | Reputational | Public incident: governed AI workflow causes harm; Verixa named in coverage | 2 | 5 | 10 | **Treat urgently:** Incident Response Plan covers customer-side incidents involving governed AI; Verixa public-comms protocol pre-drafted; documented in `docs/19_incident_response_plan/` | DPO + CEO | Per incident |
| **R-REP-02** | Reputational | Critical security disclosure not handled per public commitment | 1 | 4 | 4 | **Tolerate:** SECURITY.md publishes 72h / 7d / 30d vulnerability response SLA (CP-29a); test response annually | CTO | Annual |
| **R-REP-03** | Reputational | Marketing language drifts toward "regulator-ready" / "guarantees compliance" overclaim | 2 | 3 | 6 | **Treat:** Glossary + README + all docs use precise compliance-language posture; reviewed at every release | DPO + Marketing | Per release |

## 5. Cross-references to Threat Model

| Risk ID | Source threat (THREAT_MODEL.md) |
|---|---|
| R-SEC-01 | T-3.2 reviewer-triad collusion |
| R-SEC-02 | T-2.1 audit-ledger tampering |
| R-SEC-03 | T-4.1 per-tenant key compromise |
| R-SEC-04 | T-6.1 supply-chain attack on Verixa container |
| R-SEC-05 | T-5.1 insider threat (Verixa staff) |

Threats in THREAT_MODEL.md without a corresponding R-SEC-* entry here are either: (a) lower-severity than the impact threshold for inclusion (likelihood × impact < 5) or (b) entirely outside Verixa's scope (customer-side threat). Threats outside scope are explicitly listed in THREAT_MODEL.md §"Out of scope".

## 6. Risk-treatment workflow

1. **Identification.** Risks identified via threat-modelling, incident retrospectives, customer feedback, regulator engagement, market scanning, financial review.
2. **Analysis.** Likelihood × impact scored using §3 methodology; treatment recommendation drafted.
3. **Risk owner accepts.** Named owner accepts the score and treatment plan, or pushes back with revised assessment.
4. **Mitigations land.** Treatment actions tracked alongside other engineering / compliance work; due dates recorded.
5. **Review cadence per row.** Monthly for finance; quarterly for strategic / operational / compliance; annual for stable categories.
6. **Material changes.** Any movement in score that crosses a treatment threshold (5/10/15) triggers risk-committee review within one cycle.

## 7. Governance

- **Risk owner per row** named in column 7
- **Risk committee** meets monthly; reviews delta vs prior month; approves new entries and material score changes
- **Board-level reporting** quarterly; top-5-by-score plus all risks scoring ≥ 15
- **Annual review** of the entire register; ratification of methodology

## 8. Maintenance

This register is a living document. Updates land via:

- New entry creation when a new risk is identified
- Score updates when likelihood or impact changes
- Treatment-status updates as mitigations land or fail
- Cross-reference updates as Threat Model or other related docs evolve

Versioning: this is `v1.0` (Phase 1 baseline). Material rewrites bump major version; in-place updates use minor versions.

## 9. References

- ISO 31000:2018 Risk management — Guidelines
- ISO/IEC 31010:2019 Risk management — Risk assessment techniques
- COSO Enterprise Risk Management Framework
- `docs/11_threat_model/THREAT_MODEL.md` — adversarial threat catalogue
- `docs/13_data_protection_and_privacy/DPIA_TEMPLATE.md` — privacy-risk DPIA template
- `docs/18_sre_and_operations/SLO_SLA_SPECIFICATION.md` — availability targets (input to R-OPS-* impact scoring)
- `docs/19_incident_response_plan/DISASTER_RECOVERY_PLAN.md` — operational continuity (input to R-OPS-02 / R-OPS-03 treatment)
- `docs/19_incident_response_plan/INCIDENT_RESPONSE_PLAN.md` — incident response (input to R-REP-01 treatment)
- ADRs 0001–0010 — architectural decisions that shape several risk treatments

---

*This Risk Register is the canonical Verixa-wide risk reference. The Threat Model focuses on adversarial threats specifically. The DPIA template focuses on privacy risks specifically. This register is the superset that boards and audit committees consume.*
