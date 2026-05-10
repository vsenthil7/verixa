# Verixa — Regulatory Mapping Matrix

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: Compliance officer, Big 4 advisor, regulator-facing audit team, customer's Head of AI Governance

---

## 1. Purpose

This document maps every Verixa control to the specific regulatory and standards-body obligations it supports. It is the canonical artefact a customer's compliance team uses to:

- Demonstrate to a regulator that AI deployments governed by Verixa meet specific articles of the EU AI Act
- Crosswalk Verixa controls to NIST AI RMF Govern / Map / Measure / Manage functions
- Crosswalk to ISO/IEC 42001 AI Management System clauses
- Crosswalk to UK FCA / PRA expectations (financial services), MHRA expectations (healthcare), MoD AI Assurance (defence), Ofgem (energy), and equivalents in EU member states
- Crosswalk to OWASP AIVSS, CSA AICM, and the AAGATE reference architecture

The matrix is the operational artefact. The Compliance Dossier Generator emits per-workflow versions of this matrix as part of the Annex IV-aligned dossier output.

---

## 2. Verixa control catalogue

Verixa exposes 28 named controls grouped into seven control families. Each control has an ID, a name, the module(s) that implement it, and the regulatory obligations it supports.

**Control families:**
- VRX-GOV — Governance and policy
- VRX-RUN — Runtime interception and enforcement
- VRX-VER — AI verification
- VRX-EVD — Evidence and audit
- VRX-OPS — Human oversight and operations
- VRX-DAT — Data, retention, and disclosure
- VRX-SEC — Security and supply chain

Each control is the unit of mapping in the matrix below. A regulator question of the form "show me how you meet Article X" resolves to one or more VRX control IDs, and each VRX control ID resolves to specific Verixa modules, audit ledger evidence, and dossier sections.

---

## 3. Control catalogue

### VRX-GOV — Governance and policy

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-GOV-01 | Documented AI governance policy in regulation-as-code (Rego) | Policy Engine |
| VRX-GOV-02 | Risk classification per workflow | Workflow Registry + Risk Engine |
| VRX-GOV-03 | Sector compliance pack (financial services / healthcare / public sector / defence / energy) | Policy Engine + Compliance Dossier Generator |
| VRX-GOV-04 | Versioned policy lifecycle with test fixtures | Policy Authoring + Policy Test Harness |

### VRX-RUN — Runtime interception and enforcement

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-RUN-01 | Inline interception of every governed action | Runtime Gateway |
| VRX-RUN-02 | Tool call allow-list and argument bound enforcement | Tool Call Firewall |
| VRX-RUN-03 | Deterministic policy evaluation at runtime (OPA + Rego) | Policy Engine |
| VRX-RUN-04 | Risk-based decision routing | Risk Engine + Decision Router |
| VRX-RUN-05 | Hard-policy-breach blocking | Decision Router |

### VRX-VER — AI verification

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-VER-01 | Multi-model independent reviewer triad with hash-commitment | Triad Review Engine |
| VRX-VER-02 | Evidence and citation grounding validation | Evidence Validator |
| VRX-VER-03 | Contradiction detection across reasoning chain | Contradiction Detector (Phase 2) |
| VRX-VER-04 | Hallucination and unsupported-claim risk scoring | Hallucination Risk Engine (Phase 2) |
| VRX-VER-05 | Model drift monitoring across primary and reviewer models | Model Drift Monitor (Phase 3) |

### VRX-EVD — Evidence and audit

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-EVD-01 | Hash-chained, signed, append-only audit ledger | Audit Ledger |
| VRX-EVD-02 | Snapshot-based replay of past decisions | Replay Vault + Replay Service |
| VRX-EVD-03 | Annex IV-aligned technical dossier generation | Compliance Dossier Generator |
| VRX-EVD-04 | Per-workflow evidence reconstruction | Workflow Evidence Store |
| VRX-EVD-05 | Cross-anchor option for tamper-evident anchoring (optional) | Audit Ledger |

### VRX-OPS — Human oversight and operations

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-OPS-01 | Human review queue with full decision context | Human Review Console (Phase 2) |
| VRX-OPS-02 | Authority-based approval matrix | Approval Matrix Engine (Phase 2) |
| VRX-OPS-03 | Reviewer effectiveness tracking | Trust Graph (Phase 4) |
| VRX-OPS-04 | Managed human review operations service | WET Ops (Phase 4, optional add-on) |

### VRX-DAT — Data, retention, and disclosure

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-DAT-01 | Sector-aligned tiered retention (hot / warm / cold) | Replay Vault + retention jobs |
| VRX-DAT-02 | Per-tenant encryption with customer-managed key hierarchy option | Replay Vault + Vault integration |
| VRX-DAT-03 | Data subject access and erasure handling per DPA | Control Plane API + retention jobs |
| VRX-DAT-04 | Outbound webhook signing and customer-side verification | Webhook Event API |

### VRX-SEC — Security and supply chain

| Control ID | Control name | Implementing module(s) |
|---|---|---|
| VRX-SEC-01 | SPIFFE/SPIRE service identity for all internal services | Identity & Secrets layer |
| VRX-SEC-02 | mTLS between every pair of Verixa containers | Identity & Secrets layer |
| VRX-SEC-03 | Signed OCI images with SBOM and Cosign verification | Build pipeline + deployment |
| VRX-SEC-04 | Supply-chain provenance attestation for primary and reviewer models | Hallmark module (Phase 5) |
| VRX-SEC-05 | Sovereign deployment with no outbound egress for reviewer models (Phase 1) | Sovereign Verifier mode |
| VRX-SEC-06 | Quarterly signing key rotation with historical key retention | Audit Ledger key registry |

---

## 4. EU AI Act mapping

The EU AI Act creates obligations primarily for **providers** (Article 16) and **deployers** (Article 26) of high-risk AI systems. Verixa is positioned as the runtime substrate that enables the deployer to meet Articles 9, 12, 13, 14, 15, 17, 26, and 72, and to produce the Annex IV technical documentation. Verixa is not itself the high-risk AI system; it is the governance infrastructure for high-risk AI systems that customers deploy.

| EU AI Act provision | Obligation summary | Verixa controls |
|---|---|---|
| Article 9 — Risk management system | Establish, implement, document, and maintain a risk management system across the AI system's lifecycle | VRX-GOV-01, VRX-GOV-02, VRX-RUN-04, VRX-VER-05, VRX-EVD-01 |
| Article 10 — Data and data governance | Training, validation, testing data sets meeting quality criteria | Out of Verixa's primary scope (model training is upstream); VRX-VER-02 supports validation against retrieved data at runtime |
| Article 12 — Record-keeping | Automatic logging of events over the lifetime of the AI system | VRX-EVD-01, VRX-EVD-02, VRX-EVD-04, VRX-DAT-01 |
| Article 13 — Transparency and provision of information to deployers | Instructions for use; technical capabilities; performance characteristics | VRX-EVD-03 (dossier output supports deployer transparency obligations) |
| Article 14 — Human oversight | Effective human oversight by natural persons during the period in which the AI system is in use | VRX-OPS-01, VRX-OPS-02, VRX-RUN-04 (escalation routing), VRX-OPS-04 |
| Article 15 — Accuracy, robustness, cybersecurity | Accurate, robust, and cyber-secure throughout lifecycle | VRX-VER-01, VRX-VER-02, VRX-SEC-01..06, VRX-VER-05 |
| Article 17 — Quality management system | QMS for compliance with the regulation | VRX-GOV-03, VRX-GOV-04, VRX-EVD-03 |
| Article 18 — Documentation keeping | Retain documentation for 10 years | VRX-DAT-01 (cold tier supports 10-year retention) |
| Article 19 — Automatically generated logs | Retain logs for at least 6 months or per applicable law | VRX-EVD-01, VRX-DAT-01 |
| Article 26 — Obligations of deployers of high-risk AI | Use according to instructions, monitor operation, retain logs, ensure human oversight | VRX-RUN-01, VRX-RUN-04, VRX-OPS-01, VRX-OPS-02, VRX-EVD-01, VRX-EVD-02 |
| Article 72 — Post-market monitoring | Document, evaluate, address relevant performance issues during operation | VRX-VER-05, VRX-EVD-01, VRX-EVD-02, VRX-EVD-03 |
| Annex IV — Technical documentation | Detailed technical file: description, design, monitoring, performance, risk management | VRX-EVD-03 emits Annex-IV-aligned content; full mapping below |

### Annex IV section-by-section coverage

| Annex IV section | Content required | Verixa coverage |
|---|---|---|
| (1) General description of the AI system | Intended purpose, name, version, hardware/software | Customer-supplied; Verixa Workflow Registry stores the runtime view |
| (2) Detailed description | Methods, design choices, data, training | Customer-supplied; Verixa augments with model registry, version hashes, deployment topology |
| (3) Detailed information about monitoring, functioning, and control | How the AI system is monitored and controlled in operation | VRX-RUN-01..05, VRX-VER-01..05, VRX-OPS-01..04 evidence; auto-emitted by Compliance Dossier Generator |
| (4) Description of risk management system | Article 9 risk management documentation | VRX-GOV-01, VRX-GOV-02 evidence |
| (5) Changes through lifecycle | Versioning, updates, retraining | Verixa Policy Versioning + Model Registry version hashes; customer-supplied for primary model retraining |
| (6) List of harmonised standards applied | Standards used | VRX-GOV-03 maps Verixa controls to standards |
| (7) Copy of EU declaration of conformity | Customer's declaration | Customer-supplied; Verixa Compliance Dossier supports the technical evidence |
| (8) Detailed description of system in place to evaluate AI system performance in post-market phase | Article 72 post-market monitoring system | VRX-VER-05, VRX-EVD-01, VRX-EVD-02 evidence |

The Compliance Dossier Generator emits a complete Annex-IV-aligned technical dossier on demand. The dossier is signed with the tenant's audit ledger key, includes a hash-chain proof, and is structured per the section list above.

---

## 5. NIST AI RMF mapping

NIST AI RMF defines four functions: Govern, Map, Measure, Manage. The 2024 Generative AI Profile extends these for GenAI systems. Verixa controls map across all four:

### Govern

| NIST AI RMF Govern subcategory | Verixa controls |
|---|---|
| GOVERN 1.1 — Legal and regulatory requirements | VRX-GOV-01, VRX-GOV-03 |
| GOVERN 1.2 — Trustworthy AI characteristics integrated into policies | VRX-GOV-01, VRX-VER-01..05 |
| GOVERN 2.1 — Roles and responsibilities | VRX-OPS-02 |
| GOVERN 3.2 — Stakeholder engagement and review | VRX-OPS-01, VRX-OPS-04 |
| GOVERN 4.1 — Documented policies and procedures | VRX-GOV-01, VRX-GOV-04 |

### Map

| NIST AI RMF Map subcategory | Verixa controls |
|---|---|
| MAP 1.1 — Context of use | VRX-GOV-02 (workflow risk classification); customer-supplied use case description |
| MAP 2.3 — System task and method | Workflow Registry + Model Registry |
| MAP 3.4 — Risks identified | VRX-GOV-02, VRX-RUN-04, VRX-VER-04 |
| MAP 5.1 — Likelihood and magnitude of risk | VRX-RUN-04 (Risk Engine output) |

### Measure

| NIST AI RMF Measure subcategory | Verixa controls |
|---|---|
| MEASURE 1.1 — Test and evaluation in operation | VRX-VER-01, VRX-VER-02 |
| MEASURE 2.4 — Accountability and transparency measured | VRX-EVD-01, VRX-EVD-03 |
| MEASURE 2.7 — Security and resilience evaluated | VRX-SEC-01..06, Threat Model (separate document) |
| MEASURE 2.8 — Explainability and interpretability evaluated | VRX-VER-02 (citation grounding), VRX-EVD-02 (replay) |
| MEASURE 2.10 — Privacy risk evaluated | VRX-DAT-02, VRX-DAT-03 |
| MEASURE 3.1 — Drift and degradation in operation | VRX-VER-05 |

### Manage

| NIST AI RMF Manage subcategory | Verixa controls |
|---|---|
| MANAGE 1.3 — Treatment plans for identified risks | VRX-GOV-04 (policy lifecycle), VRX-RUN-05 (blocking) |
| MANAGE 2.3 — Incident response | VRX-OPS-01, VRX-OPS-02, VRX-EVD-02 |
| MANAGE 4.1 — Post-deployment monitoring | VRX-VER-05, VRX-EVD-01 |
| MANAGE 4.3 — Corrective and adaptive responses | VRX-GOV-04 (policy versioning), VRX-RUN-05 (blocking) |

---

## 6. ISO/IEC 42001 mapping

ISO/IEC 42001:2023 specifies AI Management System requirements. Verixa controls map to the management system clauses:

| ISO 42001 clause | Topic | Verixa controls |
|---|---|---|
| 5 — Leadership | AI policy, roles, responsibilities | VRX-GOV-01, VRX-OPS-02 |
| 6 — Planning | AI risks and opportunities, AI objectives | VRX-GOV-02, VRX-RUN-04 |
| 7 — Support | Resources, competence, awareness, communication, documented information | VRX-GOV-04, VRX-EVD-03, VRX-EVD-04 |
| 8 — Operation | AI risk assessment, AI risk treatment, AI system impact assessment | VRX-RUN-01..05, VRX-VER-01..05, VRX-OPS-01..02 |
| 9 — Performance evaluation | Monitoring, internal audit, management review | VRX-VER-05, VRX-EVD-01, VRX-EVD-03 |
| 10 — Improvement | Nonconformity, corrective action, continual improvement | VRX-VER-05, VRX-OPS-01, VRX-GOV-04 |
| Annex A controls | AI-specific controls | Crosswalk maintained as separate appendix |

---

## 7. UK sector regulator alignment

### Financial services — FCA, PRA, EBA

Verixa's financial services compliance pack supports:
- FCA SYSC (Senior Management Arrangements, Systems and Controls) — VRX-GOV-01, VRX-OPS-01, VRX-OPS-02
- PRA SS1/23 (model risk management principles for banks) — VRX-VER-01, VRX-VER-05, VRX-EVD-01
- EBA Guidelines on internal governance — VRX-GOV-01..04
- DORA (Digital Operational Resilience Act) — VRX-SEC-01..06, VRX-EVD-02

### Healthcare — MHRA, EU MDR, FDA SaMD

Verixa's healthcare compliance pack supports:
- MHRA AI as a Medical Device guidance — VRX-VER-01, VRX-VER-02, VRX-EVD-01, VRX-OPS-01
- EU MDR / IVDR — clinical evaluation evidence — VRX-VER-02, VRX-EVD-02
- FDA Predetermined Change Control Plan (for AI/ML) — VRX-VER-05, VRX-GOV-04

### Public sector — UK / EU member state

Verixa's public sector compliance pack supports:
- UK Algorithmic Transparency Recording Standard — VRX-EVD-03 dossier output
- UK AI Playbook for Government / AI Ethics frameworks — VRX-GOV-01, VRX-OPS-01..02
- EU member state public-sector AI registers (e.g. Netherlands, Spain) — VRX-EVD-03

### Defence — MoD AI Assurance

Verixa's defence compliance pack supports:
- MoD JSP 936 / Defence AI Strategy Assurance — VRX-VER-01, VRX-EVD-01, VRX-EVD-02, VRX-OPS-01..02, VRX-SEC-05 (sovereign deployment)

### Energy / CNI — Ofgem, NIS2

Verixa's energy/CNI compliance pack supports:
- NIS2 Directive operational resilience — VRX-SEC-01..06, VRX-EVD-01
- Ofgem cyber resilience expectations — VRX-SEC-01..06

---

## 8. OWASP AIVSS, CSA AICM, AAGATE crosswalk

### OWASP AIVSS (AI Vulnerability Scoring System)

Verixa's threat model (separate document) maps each STRIDE and AAGATE risk class to AIVSS scoring dimensions. Customers can produce AIVSS-formatted vulnerability reports from Verixa audit data.

### CSA AICM (AI Controls Matrix)

Verixa extends the CSA AICM by providing the runtime evidence for each AICM control. Where AICM specifies a control, Verixa provides the operational evidence that the control is in effect. The crosswalk is maintained as a CSA-formatted appendix.

### AAGATE (CSA Agentic AI Trust and Governance Architectural Tier)

Mapping Verixa modules to AAGATE's eight reference components is documented in the System Architecture Document, section 11. Briefly:

- AAGATE GOA → Verixa Decision Router + Risk Engine + Trust Graph
- AAGATE ComplianceAgent → Verixa Policy Engine + Compliance Dossier Generator
- AAGATE Janus SMA → Verixa Triad Review Engine (extended from 1 mirror to 3 reviewers)
- AAGATE Tool-Gateway Chokepoint → Verixa Runtime Gateway + Tool Call Firewall
- AAGATE Agent Name Service → Verixa SPIFFE/SPIRE
- AAGATE Service Mesh → customer's existing service mesh (Verixa does not ship Istio/Cilium)
- AAGATE Behavioural Analytics → Verixa Trust Graph + Model Drift Monitor + Risk Engine
- AAGATE ETHOS Ledger Hooks → Verixa Audit Ledger (optional cross-anchor)

---

## 9. Mapping maintenance and dossier output

This Regulatory Mapping Matrix is updated:
- On every new Verixa control addition (each phase gate)
- On any regulatory change (EU AI Act delegated acts, NIST AI RMF revisions, sector regulator guidance updates)
- On any new sector compliance pack release
- Quarterly review by Verixa Compliance Officer + customer-facing advisory board

The Compliance Dossier Generator emits a customer-and-workflow-specific version of this matrix as part of every Annex IV-aligned dossier. The customer's compliance team uses the matrix as evidence for regulator response. The matrix is signed with the tenant's audit ledger key.

---

*This Regulatory Mapping Matrix is the canonical compliance crosswalk for Verixa. The Evidence Pack Specification document defines the exact structure of dossier output. The System Architecture Document defines the modules implementing each control. Updates require Compliance Officer approval and Phase Gate review.*
