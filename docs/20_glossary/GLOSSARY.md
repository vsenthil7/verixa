# Verixa — Glossary

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: All readers of Verixa documentation

---

## Purpose

This glossary defines terms used across the Verixa documentation pack. Terms are organised alphabetically. Each definition cross-references the primary document where the term is specified in detail.

---

## A

**AAGATE** — Agentic AI Trust and Governance Architectural Tier; reference architecture published by Cloud Security Alliance in November 2025; specifies eight components and seven control loops for runtime governance of agentic AI. See: System Architecture Document §11, Regulatory Mapping Matrix §8.

**Action (governed action)** — A discrete decision or tool invocation by a customer's AI agent that passes through Verixa for runtime governance. Every governed action receives a Verixa decision (allow / deny / escalate) and an audit ledger entry. See: System Architecture Document §6.

**AICM** — AI Controls Matrix; Cloud Security Alliance control framework for AI systems; Verixa extends AICM with runtime evidence. See: Regulatory Mapping Matrix §8.

**AIVSS** — AI Vulnerability Scoring System; OWASP-aligned scoring methodology for AI vulnerabilities; Verixa supports AIVSS-format vulnerability reports. See: Threat Model §5, Regulatory Mapping Matrix §8.

**AMD Developer Cloud** — AMD's cloud platform for AMD Instinct MI300X access; the substrate for Verixa Tier 3 (sovereign managed) and Tier 4 (hosted SaaS) deployments. See: Product Vision §12, Deployment Topology §4–5.

**Annex IV** — EU AI Act Annex IV; specifies the technical documentation required for high-risk AI systems; Verixa Compliance Dossier Generator emits Annex-IV-aligned content. See: Evidence Pack Specification §3, Regulatory Mapping Matrix §4.

**Apache AGE** — Postgres extension providing graph database capabilities; Verixa's Trust Graph is implemented on Apache AGE for typical deployments. See: Data Model §9.

**API Specification** — Documented interface contract for Verixa's Runtime API, Control Plane API, and Webhook Event API. See: API Specification (entire document).

**Approval Matrix Engine** — Phase 2 module that enforces authority-based approval — who can approve what at what risk level — for human-in-the-loop decisions. See: Product Vision §9, Build Plan §4.

**Article 9 / Article 14 / Article 15 / Article 72 / Article 18** — Key articles of the EU AI Act for which Verixa controls provide implementation evidence. See: Regulatory Mapping Matrix §4.

**Audit Ledger** — Verixa's append-only, hash-chained, Ed25519-signed record of every governed action; the cryptographic source of truth for audit and regulator response. See: System Architecture Document §4, Data Model §5.

**Auditex** — MIT-licensed open-source library providing audit-chain primitives; Verixa builds on Auditex as a dependency. See: Build Plan §2 (Phase 0), README §Licensing.

---

## B

**Bench** — Phase 5 module: model and workflow evaluation harness for use-case-specific model selection. See: Build Plan §7.

**Big 4** — The four largest professional services firms (Deloitte, EY, KPMG, PwC); key advisors in regulated enterprise AI governance procurement; Verixa's Phase 1 reference programme includes Big 4 review. See: Product Vision §6, Build Plan §3.

**Build Plan** — Verixa's six-phase delivery roadmap from hackathon prototype (Phase 0) to federated trust mesh (Phase 6). See: Build Plan (entire document).

---

## C

**C4 model** — Software architecture diagramming methodology with four levels (Context, Container, Component, Code); Verixa's System Architecture Document uses C4 levels 1–3. See: System Architecture Document §2–5.

**CAIQ** — Consensus Assessments Initiative Questionnaire; Cloud Security Alliance's standardised security questionnaire for cloud service providers; Verixa publishes a CAIQ-based response template. See: Security Architecture §10.

**Celery** — Python distributed task queue; Verixa uses Celery for asynchronous background jobs (dossier generation, retention tier movement, Trust Graph rollups). See: System Architecture Document §3.

**Cilium** — eBPF-based service mesh; one of the customer-side service meshes Verixa integrates with in Phase 3 sidecar mode. Verixa does not ship Cilium. See: System Architecture Document §11, Build Plan §5.

**Compliance Dossier** — see "Evidence Pack" and "Annex IV-aligned dossier".

**Compliance Dossier Generator** — Verixa module that generates Annex IV-aligned technical dossiers from audit ledger and replay vault evidence. See: System Architecture Document §3, Evidence Pack Specification (entire document).

**Contradiction Detector** — Phase 2 module that detects contradictions across an agent's reasoning chain or across reviewer outputs. See: Product Vision §9, Build Plan §4.

**Control Plane** — The administrative, query, and reporting layer of Verixa, distinct from the hot-path Runtime Container. Hosts admin API, policy authoring, human review console, dossier generation, Trust Graph queries. See: System Architecture Document §3, §5.

**Control Plane API** — REST and GraphQL API for Verixa administrative operations. See: API Specification §3.

**Cosign** — Sigstore tool for signing and verifying container images; Verixa container images are Cosign-signed. See: Security Architecture §6.

**CSA** — Cloud Security Alliance; publisher of AAGATE, AICM, and the STAR cloud assurance programme. See: Regulatory Mapping Matrix §8.

---

## D

**Data Model** — Verixa's persistent storage schemas; Postgres-based with object store for Replay Vault. See: Data Model (entire document).

**Decision Router** — Verixa Runtime Container component that routes a governed action based on Risk Engine output and policy flags (allow / deny / escalate / triad-required). See: System Architecture Document §4.

**Deny** — Decision class meaning Verixa blocks the governed action; the customer's AI agent receives a policy violation response. See: API Specification §2.

**Deployment Topology** — The four supported Verixa deployment models (on-premises, private cloud, sovereign managed, hosted SaaS). See: Deployment Topology (entire document).

**DIRF** — Digital Identity Rights Framework; AAGATE-named risk class addressing unauthorised replication or monetisation of digital likeness. See: Threat Model §4.3.

**Dossier** — see "Compliance Dossier" and "Evidence Pack".

**DPA** — Data Processing Agreement; contractual document governing personal data handling; Verixa publishes a DPA template. See: Pricing & Commercial Model §5, Evidence Pack Specification §9.

**DORA** — Digital Operational Resilience Act (EU); financial-services regulation Verixa's financial services compliance pack supports. See: Regulatory Mapping Matrix §7.

---

## E

**Ed25519** — Edwards-curve digital signature algorithm; Verixa's signing algorithm for audit ledger entries and webhook payloads. See: Data Model §5.2, Security Architecture §4.

**Escalate** — Decision class meaning Verixa routes the governed action to human review (or higher-tier triad) before allowing or denying. See: API Specification §2.

**Evidence Pack** — Canonical archive Verixa emits to satisfy regulator, auditor, or internal audit information requests. Four pack types: per-decision, per-workflow, Annex IV dossier, Article 72 PMM. See: Evidence Pack Specification (entire document).

**Evidence Validator** — Verixa Runtime Container component that validates claims (e.g. agent-stated facts) against retrieved documents and tool outputs. See: System Architecture Document §4.

**Executive Brief** — Verixa's one-page strategic summary for buyer, investor, advisory board. See: docs/00_executive_brief/.

---

## F

**Federated Trust Mesh** — Phase 6 capability: cross-organisation trust attestation network. See: Build Plan §8.

**Forge** — Phase 5 module: policy authoring studio with natural-language to Rego compilation. See: Build Plan §7.

---

## G

**Genkit** — Framework used by AAGATE's open-source MVP dashboard; Verixa is a separate, production-grade implementation aligned with AAGATE rather than built on Genkit. See: Product Vision §3.

**Governed action** — see "Action".

---

## H

**Hallmark** — Phase 5 module: model and data provenance attestation with cryptographic verification. See: Build Plan §7.

**Hallucination Risk Engine** — Phase 2 module: scores unsupported claims and unverified assertions in agent outputs. See: Product Vision §9, Build Plan §4.

**Hash chain** — Cryptographic linking of audit ledger entries such that any tampering is detectable; each entry's `hash_chain_self` includes the prior entry's `hash_chain_self` in its inputs. See: Data Model §5.2.

**Hosted SaaS** — Tier 4 deployment topology: Verixa-operated multi-tenant on AMD Developer Cloud. See: Deployment Topology §5.

**Human Review Console** — Phase 2 module: reviewer queue UI with workflow context, evidence panel, decision capture. See: Product Vision §9, System Architecture Document §5.

**HuggingFace Spaces** — Hosted demo platform; Verixa's Phase 0 hackathon demo deploys to Hugging Face Spaces alongside MI300X demo. See: Build Plan §2.

---

## I

**ICP** — Ideal Customer Profile. Verixa's ICP: regulated UK and EU mid-to-large enterprises in financial services, healthcare, public sector, defence, energy. See: Product Vision §4.

**ISO/IEC 42001** — International standard for AI Management Systems (2023); Verixa supports customer compliance and pursues its own certification in Phase 3. See: Regulatory Mapping Matrix §6.

---

## J

**Janus Shadow Monitor** — AAGATE-specified single mirror reviewer model. Verixa's Triad Review Engine extends the Janus pattern from one mirror to three independent reviewers with hash-commit-and-reveal. See: System Architecture Document §11.

---

## L

**LangChain / LangGraph / LangSmith** — AI agent platform ecosystem; one of the workflow / agent platforms Verixa governs (complementary, not competitive). See: Competitive Landscape §3.4.

**LPCI** — Logic-layer Prompt Control Injection; AAGATE-named risk class addressing prompt injection at the logic/control layer. See: Threat Model §4.1.

---

## M

**Mesh** — Phase 6 module: federated trust network for cross-company attestations. See: Build Plan §8.

**MI300X** — AMD Instinct MI300X accelerator; 192 GB HBM3 per accelerator; Verixa's primary compute substrate for sovereign multi-model verification. See: Product Vision §12, Deployment Topology §2.

**Model Drift Monitor** — Phase 3 module: detects behavioural shifts in primary and reviewer models over time. See: Product Vision §9, Build Plan §5.

**mTLS** — Mutual TLS; Verixa enforces mTLS between every pair of internal services. See: Security Architecture §3.1, §5.1.

---

## N

**NIST AI RMF** — National Institute of Standards and Technology AI Risk Management Framework; foundational US framework for AI risk management; Verixa controls map across all four NIST AI RMF functions (Govern, Map, Measure, Manage). See: Regulatory Mapping Matrix §5.

---

## O

**OPA** — Open Policy Agent; the policy engine Verixa embeds for runtime policy decisions; uses Rego language. See: System Architecture Document §4.

**OpenAPI 3.1** — API description specification; Verixa publishes OpenAPI 3.1 specs for Runtime, Control Plane, and Webhook APIs. See: API Specification §5.

**OWASP LLM Top 10** — OWASP's Top 10 risks for Large Language Model Applications; Verixa's Threat Model cross-references each. See: Threat Model §5.

---

## P

**Per-decision pack** — Evidence Pack scoped to a single audit_id with all related context. See: Evidence Pack Specification §2.1.

**Per-workflow pack** — Evidence Pack scoped to a workflow over a time range. See: Evidence Pack Specification §2.2.

**pgvector** — Postgres extension providing vector similarity search; Verixa uses pgvector for embedding-based context lookup where needed. See: Data Model §1.

**Phase 0 / 1 / 2 / 3 / 4 / 5 / 6** — Verixa's seven build phases from hackathon prototype to federated trust mesh. See: Build Plan (entire document).

**Pilot (Tier 1)** — Verixa's £150k fixed-fee 8–12 week enterprise pilot tier. See: Pricing & Commercial Model §2.1.

**Policy Engine** — Verixa Runtime Container component using OPA + Rego for deterministic policy enforcement. See: System Architecture Document §4.

**Postgres 16** — Verixa's primary OLTP database; runs hash-chained audit ledger, policy registry, registry tables, Trust Graph (via Apache AGE). See: Data Model §1.

**PRA** — Prudential Regulation Authority (UK); financial-services regulator with model risk management expectations Verixa's financial services compliance pack supports. See: Regulatory Mapping Matrix §7.

**Product Vision** — Verixa's strategic vision document. See: Product Vision (entire document).

---

## Q

**QSAF** — Cognitive Degradation; AAGATE-named risk class addressing reasoning instability from recursive or overloaded agent sessions. See: Threat Model §4.2.

---

## R

**RBAC** — Role-Based Access Control; Verixa enforces RBAC across Control Plane API operations. See: Security Architecture §3.3.

**Rego** — Policy language used by OPA; Verixa policies are authored in Rego (regulation-as-code). See: System Architecture Document §4.

**Replay** — Reconstruction of a past Verixa decision from snapshot bundles in the Replay Vault; snapshot-based, not bit-exact regeneration. See: System Architecture Document §10.

**Replay Vault** — Verixa's content-addressable, encrypted snapshot store; backs all replay queries. See: System Architecture Document §3, Data Model §6.

**Replica** — Phase 5 module: standalone simulation and replay sandbox for pre-deployment stress testing. See: Build Plan §7.

**Risk Engine** — Verixa Runtime Container component scoring every governed action on policy + behavioural risk dimensions. See: System Architecture Document §4.

**ROCm** — AMD's open software stack for GPU computing; Verixa runs reviewer models on ROCm 7.x. See: Product Vision §12.

**Runtime Container** — The hot-path Verixa container hosting Runtime Gateway, Tool Call Firewall, Policy Engine, Risk Engine, Decision Router, Triad Review Engine, Evidence Validator, and Audit Emit. See: System Architecture Document §3.

**Runtime Gateway** — Verixa's inline interception point for every governed action; supports proxy, SDK, and sidecar integration modes. See: System Architecture Document §4.

---

## S

**SAD** — System Architecture Document. See: System Architecture Document (entire document).

**SBOM** — Software Bill of Materials; Verixa publishes SBOM per release. See: Security Architecture §6.

**SDK** — Software Development Kit; Verixa publishes Python (`verixa-python`) and TypeScript (`verixa-ts`) SDKs in Phase 1; Java and Go in Phase 2. See: API Specification §6.

**Sidecar mode** — Phase 2–3 integration mode using customer's existing service mesh (Istio, Cilium) for sidecar proxy interception. Verixa does not ship the mesh. See: Build Plan §4–5, System Architecture Document §11.

**SOC 2** — Service Organization Control 2; AICPA-defined attestation; Verixa pursues SOC 2 Type I in Phase 2 and Type II in Phase 3. See: Security Architecture §9.

**Sovereign Managed** — Tier 3 deployment topology: Verixa-operated dedicated tenancy on AMD Developer Cloud. See: Deployment Topology §4.

**Sovereign Verifier** — Verixa deployment mode in which reviewer models run on customer-controlled infrastructure with no outbound network egress. See: Security Architecture §5.1.

**SPIFFE / SPIRE** — Secure Production Identity Framework For Everyone / SPIFFE Runtime Environment; service identity standard Verixa uses for internal mTLS. See: Security Architecture §3.1.

**STRIDE** — Microsoft Security Development Lifecycle threat taxonomy (Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege); used in Verixa's Threat Model. See: Threat Model §3.

**SwarmScout** — MIT-licensed open-source library providing multi-agent coordination patterns; Verixa builds on SwarmScout as a dependency. See: Build Plan §2 (Phase 0), README §Licensing.

---

## T

**Tier 0 / Tier 1 / Tier 2 / Tier 3 / Tier 4** — Verixa's pricing tiers (Research, Pilot, Enterprise, Sovereign Managed, Hosted SaaS). See: Pricing & Commercial Model §2.

**Tool Call Firewall** — Verixa Runtime Container component validating tool calls against allow-list and argument bounds. See: System Architecture Document §4.

**Triad Review Engine** — Verixa module spawning three independent reviewer models with hash-commit-and-reveal protocol for high-risk decisions. See: System Architecture Document §4.

**Trust Graph** — Verixa's persistent property-graph capturing long-term operational memory of workflows, agents, models, reviewers, suppliers, incidents, and approvals. See: Product Vision §10, Data Model §9.

---

## V

**Vault (HashiCorp)** — Secret and encryption-key management; Verixa uses Vault for signing keys, encryption keys, and other secrets. See: Security Architecture §4.3.

**vLLM** — High-throughput LLM serving framework; Verixa uses vLLM-on-ROCm for reviewer model inference on MI300X. See: System Architecture Document §3.

**VRX-XXX-NN** — Verixa control identifier convention; e.g. VRX-RUN-01 = Inline interception of every governed action. See: Regulatory Mapping Matrix §3.

---

## W

**WET Ops** — Phase 4 module: Workflow Evidence and Trust Operations; managed human review service tier. See: Build Plan §6.

**Workflow** — A registered customer AI workflow governed by Verixa; has a risk classification, applicable policies, and escalation policy. See: Data Model §3.2.

**Workflow Evidence Store** — Verixa module providing per-workflow evidence reconstruction. See: Product Vision §9.

---

## Z

**Zero-trust** — Architectural principle: no service or actor is implicitly trusted; every interaction is authenticated and authorised. Verixa enforces zero-trust internally and assumes customer's AI agents are untrusted by default. See: Security Architecture §2.

---

*This Glossary is the canonical terminology reference for Verixa. Updates are made as new modules and capabilities ship in subsequent phases. Cross-references point to the primary document where each term is specified in detail.*
