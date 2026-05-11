# Verixa — RACI / Ownership Map

> Governance reference: who is **Responsible**, **Accountable**, **Consulted**, **Informed** for every Verixa domain. ITIL 4 + COBIT 2019 governance pattern.
>
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 baseline · Audience: All stakeholders, customer's governance team, audit

---

## 1. Purpose

Buyers' governance teams ask "who at Verixa is accountable for X?" For a Phase 0 single-author project this is degenerate (one name fills every cell). For Phase 1+ multi-role organisation, the answer matters: who signs the DPA, who owns the audit response, who decides on a security disclosure, who can authorise an emergency change.

This document is forward-looking — it specifies the role structure Verixa is hiring into, not the current single-author state. Phase 0 reality is documented honestly in §6.

## 2. RACI legend

- **R — Responsible** — does the work; can be more than one
- **A — Accountable** — answerable for the outcome; exactly one per row
- **C — Consulted** — provides input; two-way communication; can be multiple
- **I — Informed** — kept up-to-date; one-way communication; can be multiple

Each row has exactly one **A**. Anything else is a process bug.

## 3. Role definitions

- **CEO** — strategic direction, fundraising, board, customer relationships at C-level
- **CTO** — engineering direction, architecture, security posture, technology partnerships
- **DPO** — data protection, privacy program, customer DPA, regulator engagement (privacy)
- **Compliance Lead** — compliance program (SOC 2, ISO 27001, ISO 42001), audit response, regulator engagement (non-privacy)
- **SRE Lead** — production operations, SLOs, incident response, DR, change management
- **Engineering Lead** — feature delivery, code review, technical debt, engineering velocity
- **Security Lead** — security architecture, threat model, security incidents, pen-test program
- **Head of Product** — product roadmap, design partner program, product analytics
- **CRO** — revenue, customer acquisition, sales motion
- **CFO** — finance, runway, vendor contracts, board financial reporting
- **Risk Committee** — cross-functional body chaired by CEO; monthly meeting per `RISK_REGISTER.md` §7

## 4. RACI matrix

### 4.1 Product + engineering

| Domain | CEO | CTO | Eng Lead | SRE Lead | Sec Lead | Product | DPO | Compliance |
|---|---|---|---|---|---|---|---|---|
| Product roadmap | C | C | C | I | C | **A**/R | C | C |
| Architectural decision (ADR) | I | **A** | R | C | C | C | C | C |
| Code-review process | I | **A** | R | C | C | I | I | I |
| Feature deployment (standard change) | I | I | **A**/R | C | I | C | I | I |
| Feature deployment (normal change) | I | C | R | C | C | **A** | C | C |
| Emergency change (P0 / security) | C | **A** | R | R | R | I | I | I |
| Test coverage policy | I | **A** | R | C | C | I | I | I |
| Negative-test target setting | I | C | R | C | **A** | C | I | C |

### 4.2 Reliability + security

| Domain | CEO | CTO | Eng Lead | SRE Lead | Sec Lead | Product | DPO | Compliance |
|---|---|---|---|---|---|---|---|---|
| SLO setting | I | C | C | **A**/R | I | C | I | I |
| SLA commitment (per-tier) | C | **A** | I | R | I | C | C | C |
| P0 incident response | C | C | R | **A** | R | I | C | C |
| Disaster recovery procedures | I | C | I | **A**/R | C | I | C | C |
| Security vulnerability disclosure | C | C | R | C | **A**/R | I | C | C |
| Penetration test program | I | C | I | C | **A**/R | I | C | C |
| Bug-bounty program (Phase 2+) | I | C | I | C | **A**/R | I | I | I |
| Security incident (data exposure) | C | C | R | R | **A**/R | I | C | C |
| Vault key custody (per ADR-0008) | I | **A** | I | R | R | I | C | C |

### 4.3 Privacy + compliance

| Domain | CEO | CTO | Eng Lead | SRE Lead | Sec Lead | Product | DPO | Compliance |
|---|---|---|---|---|---|---|---|---|
| Customer DPA signing | C | C | I | I | I | I | **A**/R | C |
| Data-subject rights response | I | I | R | I | I | I | **A**/R | C |
| Personal-data breach notification | C | C | I | R | C | I | **A**/R | C |
| Sub-processor change | I | C | I | C | C | I | **A** | R |
| SOC 2 audit response | I | C | C | C | C | I | C | **A**/R |
| ISO 27001 / 42001 audit response | I | C | C | C | C | I | C | **A**/R |
| Customer-facing compliance evidence | I | C | I | I | C | I | C | **A**/R |
| Regulator (privacy) engagement | C | C | I | I | I | I | **A**/R | C |
| Regulator (non-privacy) engagement | C | C | I | I | I | I | C | **A**/R |

### 4.4 Business

| Domain | CEO | CTO | CFO | CRO | Product | Risk Cmte |
|---|---|---|---|---|---|---|
| Strategic direction | **A**/R | C | C | C | C | C |
| Annual budget | C | C | **A**/R | C | C | I |
| Customer pricing (standard) | C | I | C | **A**/R | C | I |
| Customer pricing (bespoke) | **A** | C | R | R | C | C |
| Sub-processor contract | I | C | R | I | I | **A** (review) |
| Risk-register entry creation | I | C | C | C | C | **A**/R |
| Risk-treatment approval (score ≥ 10) | C | C | C | C | C | **A**/R |
| Risk-treatment approval (score ≥ 15, board escalation) | **A** | R | R | R | I | R |
| Fundraising | **A**/R | I | R | I | I | C |
| Board reporting | **A**/R | R | R | R | R | R |

### 4.5 Customer-facing

| Domain | CEO | CTO | CRO | DPO | Compliance | SRE Lead | Product |
|---|---|---|---|---|---|---|---|
| Customer acquisition | C | I | **A**/R | I | I | I | C |
| Customer onboarding | I | C | R | C | C | C | **A** |
| Design-partner program | C | C | C | I | I | I | **A**/R |
| Customer SLA breach response | I | C | C | I | I | **A**/R | C |
| Customer-success engagement | I | I | **A** | I | I | I | R |
| Customer renewal | C | I | **A**/R | I | I | I | C |

## 5. Decision-authority thresholds

Beyond the RACI matrix, certain decisions require named-individual authorisation regardless of role.

| Decision | Authoriser | Notes |
|---|---|---|
| Production deployment | SRE Lead (standard); CTO (high-risk normal) | per CHANGE_MANAGEMENT_PROCESS.md |
| Emergency change | SRE Lead + Engineering Lead jointly | CAB post-hoc within 48h |
| Public security disclosure | Security Lead with CTO sign-off | per SECURITY.md |
| Customer-facing public statement during incident | CEO + DPO | crisis communications |
| Sub-processor change (non-emergency) | DPO + Compliance Lead | 30-day customer notice |
| Sub-processor change (emergency) | DPO + CTO | shortened notice with mitigation |
| Pricing change | CRO (standard); CEO + CFO (bespoke > £500K) | |
| Hiring (Engineering) | Engineering Lead + CTO | |
| Hiring (Compliance / DPO) | DPO + CEO | independence of DPO role preserved |
| Vendor contract > £100K/year | CFO + CTO (if technical) | |
| Material risk acceptance (score ≥ 15) | CEO + Risk Committee | board-informed |
| Article 36 (GDPR) supervisor consultation | DPO with CEO informed | |

## 6. Phase 0 reality (honest documentation)

Phase 0 (hackathon prototype, 2026-04 to present): **one individual (v_sen) fills every role.** The RACI structure above is the design Verixa is **hiring into**, not the current state. This is documented honestly:

- Buyers' procurement teams asking "who is your DPO?" hear: "Phase 0 is pre-revenue; for Phase 1 with first paid customer, a named DPO is part of the hiring plan; current single-author state means responsibility is concentrated; the documentation that survives the role-fill is the canonical decision record (ADRs + this RACI document + the Risk Register)."
- Risk-register entry R-OPS-04 ("single-person dependency") tracks this risk explicitly with score 20 (likelihood 5 × impact 4) — the highest active risk on the register. Mitigation: docs-hardening (CP-25 → CP-30) + Phase 1 hires + ADRs preserving decision context.

This honest disclosure is part of the trust posture, not a hidden weakness.

## 7. Review cadence

- **Annual review** of role definitions + RACI matrix by Risk Committee
- **Per-hire update** of role assignments when filling a named role
- **Per-org-change** update when team structure changes materially
- **Per-audit cycle** verification that named role-holders sign their roles' documents

## 8. References

- ITIL 4 — Roles and competencies
- COBIT 2019 — RACI mapping pattern
- ISO/IEC 38500 — IT governance
- `docs/11_threat_model/RISK_REGISTER.md` §7 — Risk Committee charter
- `docs/18_sre_and_operations/CHANGE_MANAGEMENT_PROCESS.md` — CAB role-composition
- `docs/13_data_protection_and_privacy/DATA_PROTECTION_AND_PRIVACY.md` — DPO responsibilities under GDPR
- `docs/SECURITY.md` — security-disclosure authorisation chain

---

*This RACI document is the canonical accountability reference. Phase 0 single-author state is documented honestly (§6) so a reader is not misled. Phase 1+ multi-role state is the design target.*
