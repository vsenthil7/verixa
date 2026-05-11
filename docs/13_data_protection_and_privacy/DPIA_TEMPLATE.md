# Verixa — Data Protection Impact Assessment (DPIA) Template

> Companion to `DATA_PROTECTION_AND_PRIVACY.md` §12.
> Document version: 1.0 · Date: 2026-05-11 · Status: Phase 1 template · Audience: Customer DPO

This is the structured DPIA template a customer's Data Protection Officer (DPO) completes when adopting Verixa for a high-risk AI workflow. GDPR Article 35 requires a DPIA for processing "likely to result in a high risk to the rights and freedoms of natural persons" — agentic AI workflows generally meet this threshold (ICO + EDPB guidance, ICO Big Data + AI guidance, EDPB Guidelines 9/2020).

The template aligns with the **ICO DPIA template** (UK) and the **EDPB Guidelines on Data Protection Impact Assessment** (EU). Customer DPOs can use this verbatim or adapt to their internal DPIA format.

---

## Section A — Identifying the need for a DPIA

### A.1 Brief description of the processing

> Describe the nature of the processing.
>
> *Customer prompt:* What does the AI workflow do? Whose personal data is processed? Where does the data come from? Who has access?

**Verixa-specific text the customer can include verbatim:**

The processing involves a primary AI agent (operated by [customer]) that makes decisions affecting data subjects. Verixa acts as a governance layer between the agent and downstream systems (tools, document stores, output channels). For every governed action, Verixa records:

- The input context (request envelope: agent identity, action category, retrieved documents references, tool call arguments)
- The policy evaluations (which OPA rules applied + outcomes)
- The risk score (composite metric driving routing decisions)
- The triad review (where escalated; consensus or split + per-reviewer verdicts under cryptographic commit-reveal)
- The final decision (allow / deny / escalate-to-human) + reasoning
- The encrypted replay bundle (AES-256-GCM sealed snapshot for forensic replay)

Verixa is the **data processor** acting on customer's documented instructions. The customer is the **data controller**.

### A.2 Why a DPIA is required

> Identify the GDPR Article 35 triggers that apply.

Tick all that apply:

- [ ] **A.2.1** — Systematic and extensive evaluation of personal aspects based on automated processing including profiling (Article 35(3)(a))
- [ ] **A.2.2** — Processing of special category data on a large scale (Article 35(3)(b))
- [ ] **A.2.3** — Systematic monitoring of publicly accessible area on a large scale (Article 35(3)(c))
- [ ] **A.2.4** — Use of new technologies (ICO list)
- [ ] **A.2.5** — Decisions producing legal or significant effects on data subjects (Article 22 candidate)
- [ ] **A.2.6** — Combining or matching datasets from different sources
- [ ] **A.2.7** — Processing of data of vulnerable subjects (children, employees in power-imbalanced relationships, etc.)
- [ ] **A.2.8** — Innovative use of technology including AI / machine learning
- [ ] **A.2.9** — Other — describe: ____________________________________

Most agentic AI workflows trigger A.2.4 + A.2.8 at minimum.

### A.3 Consultation requirements

> Who must be consulted before the processing begins?

- [ ] Data subjects (or their representatives) — typically via privacy notice; sometimes via direct consultation for high-risk processing
- [ ] Internal DPO + privacy team
- [ ] Information security team
- [ ] Business owner of the AI workflow
- [ ] External experts (privacy counsel, ICO/regulator consultation if required)

---

## Section B — Describing the processing

### B.1 Nature of the processing

> What are you doing with the data? Collection, storage, use, retention?

For Verixa-governed processing:

| Phase | What happens to personal data |
|---|---|
| Pre-governance | Customer's primary AI agent retrieves and processes personal data per customer's lawful basis |
| Governance | Verixa receives a request envelope (typically containing references / pseudonyms, not raw subject data) + records policy + risk + triad outcomes |
| Storage | Audit Ledger (Postgres, append-only, hash-chained, 7-year retention default); Replay Vault snapshots (AES-256-GCM, per-tenant keys, MinIO/S3, 7-year retention default) |
| Use | Decision routing (allow/deny/escalate); evidence generation; replay reconstruction on auditor request |
| Retention | Per customer DPA; cryptographic-erasure available via per-subject key destruction |
| Disposal | Cryptographic erasure of per-subject keys renders replay bundles unreadable; audit ledger entries remain (regulatory retention) |

### B.2 Scope of the processing

> What is the scope? Nature of data, volume, frequency, geography?

- **Data categories:** customer-determined; typically reference identifiers (not raw subject data); see DATA_PROTECTION_AND_PRIVACY.md §3 for the canonical list
- **Volume:** customer-determined; Verixa scales horizontally per tenant
- **Frequency:** real-time (every governed action produces an audit row + a replay snapshot)
- **Geography:** customer-determined; Verixa deployment topology controls data residency (Tier 1 on-prem, Tier 3 sovereign region, Tier 4 customer-elected region)
- **Duration of processing:** continuous for the duration of the customer's contract; retained per retention policy

### B.3 Context of the processing

> Where does the data come from? What relationships exist with the data subjects? What is the nature of the relationship?

- **Source:** customer's primary AI workflow (Verixa never collects personal data directly from data subjects)
- **Data subject relationship:** customer-determined (e.g. customer-as-bank to data-subject-as-bank-customer; customer-as-hospital to data-subject-as-patient; customer-as-government-agency to data-subject-as-citizen)
- **Expectations of data subjects:** typically the privacy notice the customer issues; Verixa contributes the AI-governance-processing scaffold (DATA_PROTECTION_AND_PRIVACY.md §11)

### B.4 Purposes of the processing

> Why are you doing it? What outcomes do you expect to achieve?

- Ensuring the AI workflow's actions comply with customer's policies + applicable law
- Producing audit-grade evidence the customer can review or share with regulators on request
- Reconstructing past decisions for forensic, dispute-resolution, or audit purposes
- Catching policy violations + risky actions before they execute (preventive governance)

---

## Section C — Necessity and proportionality

### C.1 Lawful basis

> What is the lawful basis for the processing?

Customer-determined. See DATA_PROTECTION_AND_PRIVACY.md §4 for support of each lawful basis category.

### C.2 Necessity test

> Is the processing necessary to achieve the purposes?

Document why each personal-data category Verixa processes is necessary for the governance purpose. Categories that aren't necessary should be excluded from the request envelope at customer's source — not transmitted to Verixa.

| Personal data category | Necessity rationale |
|---|---|
| [Category 1] | [Why this is necessary for governance] |
| [Category 2] | ... |

### C.3 Proportionality test

> Is the processing proportionate to the purposes? Could you achieve the purposes with less data or less invasive processing?

Verixa's design supports proportionality through:

- **Minimisation:** request envelope contains references where possible, not raw subject data
- **Pseudonymisation:** subject identifiers in audit ledger are typically hash references; raw identifiers in replay vault are AES-256-GCM encrypted
- **Aggregation:** operator dashboards aggregate across decisions; raw subject data not exposed in dashboards
- **Differential access:** RBAC restricts which operator roles can decrypt replay bundles; pen-test report + audit log evidence available
- **Cryptographic erasure:** per-subject key destruction renders subject's replay bundles unreadable without touching the audit ledger

### C.4 Alternatives considered

> What alternatives to this processing were considered? Why is Verixa the chosen approach?

Document customer-specific alternatives. Typical alternatives:

- No governance layer (rejected — audit-grade evidence not produced; regulatory exposure)
- Internal-built governance layer (rejected — engineering cost; non-standard evidence format; no third-party-verifiable signatures)
- Competing governance product [X] (rejected — reason)

---

## Section D — Identifying and assessing risks

> Identify risks to data subjects. Score each risk on likelihood (1-3) × severity (1-3) = score 1-9.

The Verixa **Threat Model** document is the canonical source for the threats Verixa addresses + the threats outside Verixa's scope. Customer's DPIA should cite the Threat Model + add customer-specific risks.

### D.1 Risk register template

| # | Risk to data subjects | Likelihood (1-3) | Severity (1-3) | Score | Source |
|---|---|---|---|---|---|
| R-01 | Unauthorised access to replay bundle reveals subject data | 1 (multi-layer crypto + RBAC) | 3 (significant) | 3 | Verixa Threat Model T-1.1 |
| R-02 | Audit ledger tampering hides illegal processing | 1 (hash chain + Ed25519) | 3 (significant) | 3 | Verixa Threat Model T-2.1 |
| R-03 | Triad reviewers collude on incorrect verdict | 2 (heterogeneous models Phase 2; Phase 1 same model) | 2 (moderate) | 4 | Verixa Threat Model T-3.2 |
| R-04 | Customer's primary AI agent transmits more personal data than necessary | 2 (depends on customer's data minimisation discipline) | 2 (moderate) | 4 | Customer responsibility |
| R-05 | Verixa staff access to customer data in Tier 4 multi-tenant | 1 (per-tenant key hierarchy, customer-managed-key option) | 3 (significant) | 3 | DATA_PROTECTION_AND_PRIVACY.md §5 |
| R-06 | Sub-processor breach affecting Verixa-stored data | 2 (sub-processor TOMs) | 3 (significant) | 6 | DATA_PROTECTION_AND_PRIVACY.md §8 |
| R-07 | Cross-border transfer ruling (Schrems-class) invalidates current transfer mechanism | 2 (existing legal precedent) | 2 (moderate) | 4 | DATA_PROTECTION_AND_PRIVACY.md §7 |
| R-08 | Article 17 erasure request cannot be fulfilled due to regulatory retention conflict | 3 (common pattern) | 2 (moderate; mitigated by cryptographic erasure) | 6 | DATA_PROTECTION_AND_PRIVACY.md §6.3 |
| R-09 | Data subject's automated decision under Article 22 contested | 2 (depends on workflow design) | 3 (significant if no human review path) | 6 | Customer's Article 22 obligations + Verixa UC-11 |
| R-10 | [Customer-specific risk #1] | | | | |

Customer's DPO completes R-10+ with workflow-specific risks.

### D.2 Risk scoring guidance

**Likelihood (1-3):**
- 1 = Unlikely given current controls
- 2 = Possible given current controls
- 3 = Likely given current controls

**Severity (1-3):**
- 1 = Minor inconvenience to data subject
- 2 = Moderate impact (distress, reputational harm, time cost)
- 3 = Significant impact (financial loss, legal effect, physical safety, discrimination, freedom of choice)

**Score interpretation:**
- 1-3 = Low — proceed with documented mitigations
- 4-6 = Medium — strengthen mitigations or accept with documented residual risk
- 7-9 = High — reduce risk before processing or seek regulator consultation (Article 36)

---

## Section E — Identifying measures to reduce risks

> For each medium / high risk identified in Section D, document the mitigation.

| Risk # | Mitigation | Mitigation owner | Residual likelihood × severity = score |
|---|---|---|---|
| R-01 | AES-256-GCM per-tenant + Ed25519 signed audit chain + RBAC + mTLS + audit logs of every decrypt | Verixa TOMs (DATA_PROTECTION_AND_PRIVACY.md §5) | 1 × 3 = 3 |
| R-02 | Hash-chained audit ledger + standalone offline verifier (`tools/audit_verify.py`) + Ed25519 signatures | Verixa TOMs | 1 × 3 = 3 |
| R-03 | Commit-reveal protocol + Phase 2 heterogeneous reviewer rollout (ADR-0002 + future ADR-0011) | Verixa product roadmap | 1 × 2 = 2 |
| R-04 | Customer data-minimisation discipline + Verixa request envelope schema enforces field caps (API_STYLE_GUIDE §3.5) | Joint: customer + Verixa | 1 × 2 = 2 |
| R-05 | Per-tenant key hierarchy + customer-managed-key option for Tier 1-3 (ADR-0008) + Verixa staff cannot decrypt | Verixa TOMs + ADR-0008 | 1 × 3 = 3 |
| R-06 | Sub-processor flow-down contractual TOMs + sub-processor audit rights + 30-day change notification | DATA_PROTECTION_AND_PRIVACY.md §8 | 1 × 3 = 3 |
| R-07 | Tier 1 + Tier 3 sovereign deployments avoid cross-border transfers entirely; for cloud deployments, SCCs + DPF where applicable | Customer's deployment topology choice | 1 × 2 = 2 |
| R-08 | Cryptographic erasure: subject's replay bundles unreadable while audit ledger retained for regulatory purpose; DPA documents the conflict-resolution | DATA_PROTECTION_AND_PRIVACY.md §6.3 + DPA | 2 × 1 = 2 |
| R-09 | UC-11 human-in-the-loop approval matrix + triad escalation for high-risk decisions + audit replay supports Article 22 explainability | Verixa UC-11 (ADR-0009) | 1 × 3 = 3 |
| R-10 | [Customer-specific mitigation] | | |

Document any risks where residual score remains ≥ 7 in Section F.

---

## Section F — Sign-off and decision

### F.1 DPO advice

> Has the DPO been consulted on this DPIA?

- [ ] Yes — DPO advice attached
- [ ] N/A — no statutory DPO; senior privacy lead consulted; advice attached

DPO recommendation:

- [ ] Proceed without modification
- [ ] Proceed with stated mitigations
- [ ] Reduce risk further before proceeding
- [ ] Consult supervisory authority (Article 36 prior consultation)

### F.2 Senior leadership decision

> Who authorises the processing to proceed?

| Decision | Authoriser | Date | Signature |
|---|---|---|---|
| Proceed | [name + role] | [date] | [signature] |

### F.3 Supervisory authority consultation (if required)

If any residual risk remains ≥ 7 after mitigation, Article 36 prior consultation with the supervisory authority is required.

- [ ] Prior consultation required → consultation requested on [date]; outcome attached
- [ ] Prior consultation not required (residual risks all < 7)

### F.4 Review schedule

> When will this DPIA be reviewed?

- **Default review cadence:** annually
- **Triggered reviews:** material change in the AI workflow, material change in Verixa's TOMs, regulatory or legal change, post-incident
- **Next scheduled review:** [date]

---

## Section G — Maintenance

This DPIA is a living document. Updates land via the customer's standard document control process. Each version retained for the duration of the processing + retention period thereafter.

Verixa supports customer's DPIA maintenance by:

- Notifying customer of material TOMs changes (DATA_PROTECTION_AND_PRIVACY.md §8.2 30-day notice cadence applies to sub-processor changes)
- Publishing roadmap changes affecting privacy posture (e.g. ADR-0007 SPIRE rollout, ADR-0008 key custody changes, future Phase 2 heterogeneous triad)
- Providing updated penetration test summaries + SOC 2 / ISO 27001 / ISO 42001 attestations annually (where available)

---

## References

- `DATA_PROTECTION_AND_PRIVACY.md` — canonical privacy reference
- `docs/11_threat_model/THREAT_MODEL.md` — threats this DPIA addresses
- `docs/10_security_architecture/SECURITY_ARCHITECTURE.md` — TOMs detail
- `docs/12_compliance_and_audit/COMPLIANCE_AND_AUDIT.md` — regulatory mapping
- `docs/03_regulatory_and_compliance_baseline/REGULATORY_AND_COMPLIANCE_BASELINE.md` — retention norms
- `docs/07_system_architecture/adr/ADR-0007-spire-workload-attestation-vs-api-keys.md` — auth roadmap
- `docs/07_system_architecture/adr/ADR-0008-vault-vs-cloud-kms-for-key-custody.md` — key custody roadmap
- `docs/07_system_architecture/adr/ADR-0009-approval-matrix-routing-rules.md` — UC-11 human-in-the-loop roadmap
- ICO DPIA guidance: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/data-protection-impact-assessments-dpias/
- EDPB Guidelines 9/2020 on data protection impact assessment: https://edpb.europa.eu/our-work-tools/general-guidance/guidelines-recommendations-best-practices_en

---

*This DPIA template is provided as customer support material. The DPIA itself is the customer's accountability under Article 35; Verixa supports completion but does not approve or authorise the customer's DPIA. The customer's DPO is the accountable party for the DPIA outcome.*
