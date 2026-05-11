# Verixa — Build Plan

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 0–1 detailed; Phase 2–6 outlined · Audience: Engineering lead, Chief Architect, customer-facing delivery, board

---

## 1. Phasing overview

The architecture is full-platform from day one. The build is phased across seven phases (Phase 0 plus Phase 1–6). Each phase delivers a coherent capability surface that customers can buy, deploy, and operate; subsequent phases extend the substrate.

| Phase | Identity | Headline capability | Build window | Customer commitment |
|---|---|---|---|---|
| 0 | Hackathon prototype + GitHub-FIRST | AMD Developer Hackathon submission, public repo, Hugging Face Spaces demo | 5–10 May 2026 | Reference / evidence |
| 1 | Runtime Governance Core | Runtime Gateway, Policy Engine, Risk Engine, Decision Router, Audit Ledger, Replay Vault, Triad Review, Evidence Validator, basic Compliance Dossier | Q3–Q4 2026, 8–12 weeks per pilot | £150k pilot |
| 2 | Enterprise Control Plane | Human Review Console, Approval Matrix, full Compliance Dossier, Contradiction Detector, Hallucination Risk Engine, RBAC, sector compliance packs, input controls | Q1 2027 | £500k+ enterprise |
| 3 | Sovereign Runtime | Sovereign deployment hardening, Model Drift Monitor, sidecar / service-mesh integration mode, SOC 2, ISO 27001, ISO 42001 | Q2–Q3 2027 | Sovereign Managed tier |
| 4 | Trust Graph + Human Ops | Trust Graph at full scope, WET Ops, reviewer effectiveness, workflow anomaly detection | Q4 2027 | Trust Graph add-ons |
| 5 | Third-party AI Governance | Bench, Hallmark, Forge, Replica, third-party AI wrappers (Copilot, Salesforce, ServiceNow) | Q1–Q2 2028 | Third-party governance add-ons |
| 6 | Federated Trust Mesh | Mesh, cross-org attestation, supplier evidence sharing | Q3–Q4 2028 | Trust mesh participation |

This document details Phase 0 and Phase 1 in full; Phases 2–6 are outlined at the level of capability, deliverables, and dependency.

---

## 2. Phase 0 — Hackathon prototype + GitHub-FIRST

**Window:** 5–10 May 2026 (AT-Hack0017 series)
**Submission deadline:** 2026-05-10 20:00 BST
**Headline:** Working Verixa Phase 1 prototype with sovereign on-MI300X demo, public GitHub repository, Hugging Face Spaces deployment, hackathon submission package.

### 2.1 Phase 0 goals

1. Hackathon submission against AMD Developer Cloud / AMD Instinct MI300X hackathon brief
2. Public, MIT-licensed GitHub repository as the canonical Verixa codebase
3. Reference deployment on Hugging Face Spaces and live MI300X demo
4. Documentation pack (this document set) accessible from repo
5. Reproducible build via Docker Compose (dev) and Kubernetes (prod-ready)

### 2.2 Phase 0 deliverables

- **Codebase:**
  - Runtime Gateway (FastAPI) with `/v1/runtime/govern` and OpenAI-compatible proxy
  - Tool Call Firewall with allow-list and argument-bound enforcement
  - Policy Engine (OPA + Rego) embedded
  - Risk Engine (deterministic baseline scoring; Trust Graph deferred to Phase 4)
  - Decision Router with low/medium/high routing logic
  - Triad Review Engine with hash-commit-and-reveal protocol against three reviewer models on MI300X
  - Evidence Validator with citation grounding check
  - Audit Ledger with hash-chain + Ed25519 signing
  - Replay Vault with object-store snapshot bundles
  - Basic Compliance Dossier Generator (per-decision pack)
  - Control Plane API skeleton (workflow registry, agent registry, audit query, dossier generate)
  - Next.js 14 + Tailwind + shadcn/ui Control Plane UI with workflow list, audit query, replay viewer, dossier download
- **Infrastructure:**
  - Docker Compose dev environment (one-command up)
  - Kubernetes Helm charts for production-ready deployment
  - Postgres 16 + pgvector schema migrations (Alembic)
  - Redis for rate limits and OPA cache
  - HashiCorp Vault dev-mode container
- **Documentation:**
  - Executive Brief, Product Vision, Competitive Landscape, Pricing
  - System Architecture Document, API Specification, Data Model, Threat Model
  - Regulatory Mapping Matrix, Evidence Pack Specification
  - this Build Plan
  - README at project root
  - Optional: Security Architecture, Deployment Topology, SRE & Operations, Glossary
- **Tests:**
  - pytest backend unit + integration coverage on the hot path
  - Vitest frontend coverage on key UI flows
  - Playwright E2E for the canonical "register workflow → submit governed action → verify audit + replay → download dossier" scenario

### 2.3 Phase 0 dependency graph

```text
[hackathon brief lock]
        |
        v
[architecture lock] <-- 2026-05-10 02:41 ✅
        |
        v
[documentation pack] <-- in progress ✅ (this document)
        |
        v
[GitHub-FIRST repo init] --+
        |                   |
        v                   v
[Phase 1 codebase]    [Hugging Face Spaces deploy]
        |                   |
        v                   v
[demo recording]    [submission package]
        |                   |
        +---------+---------+
                  |
                  v
        [submission @ 20:00 BST]
```

### 2.4 Phase 0 risks

- **Time budget:** ~16 hours from documentation pack completion to submission deadline. Risk: scope creep in code work. Mitigation: hot-path-first build, Triad Review uses shorter reviewer models in demo if time-pressured (full triad is architectural; demo models are workload-tuned).
- **MI300X availability:** AMD Developer Cloud capacity. Mitigation: Hugging Face Spaces fallback for reviewer models if MI300X unavailable; demo recording covers both.
- **Documentation drift:** code may diverge from docs in the rush. Mitigation: docs lock at end of doc-writing run; any code-doc drift is logged in a known-deviations file delivered with submission.

---

## 3. Phase 1 — Runtime Governance Core (post-hackathon, customer pilot)

**Window:** Q3–Q4 2026, 8–12 weeks per pilot engagement
**Headline:** First commercial pilot deployment with regulated UK/EU enterprise customer.

### 3.1 Phase 1 goals

1. £150k fixed-fee pilot delivered against one customer's high-value regulated workflow
2. Pilot success criteria met: regulator-acceptable Compliance Dossier, replay demonstration, joint test plan completion
3. Conversion to Tier 2 Enterprise contract (target 60%+ pilot conversion rate)

### 3.2 Phase 1 deliverables (in addition to Phase 0)

- **Customer-deployment-grade hardening:**
  - Production-grade Postgres HA (primary + 2 read replicas, Patroni failover)
  - Production-grade object store (customer S3-compatible or MinIO with erasure coding)
  - Production-grade Vault integration with customer-managed key hierarchy
  - mTLS + SPIFFE/SPIRE service identity in customer environment
  - Customer IAM (OIDC/SAML) integration for Control Plane
  - Webhook event API to customer SIEM and ITSM
  - Operational runbook + incident-response playbook
- **Pilot-specific:**
  - Customer's Rego policy library authored against their workflow + sector compliance pack
  - Workflow registration + tool registration + agent registration
  - Joint test plan with customer's compliance + audit functions
  - Pilot success criteria document with explicit metrics
  - Final pilot report with regulator-engagement-ready output
- **SDK + integration:**
  - `verixa-python` SDK published to PyPI
  - `verixa-ts` SDK published to npm
  - OpenAI-compatible proxy validated against customer's primary model providers

### 3.3 Phase 1 dependency graph

```text
[Phase 0 prototype] ✅
        |
        v
[customer pilot scoping] (sales motion)
        |
        v
[pilot SOW + success criteria signed]
        |
        v
[customer environment provisioning]  --- (customer IAM, Vault, MI300X, network)
        |
        v
[Verixa deployment in customer env]
        |
        v
[customer policy authoring]  ---- (Verixa team + customer compliance)
        |
        v
[workflow registration + agent integration]
        |
        v
[pilot operation period]
        |
        v
[joint test plan execution]
        |
        v
[pilot success review + Tier 2 conversion]
```

### 3.4 Phase 1 risks

- **Customer environment delay:** customer's IAM, Vault, network, MI300X provisioning typically takes 2–4 weeks. Mitigation: pre-pilot environment readiness checklist; sales engagement de-risks before SOW signing.
- **Policy authoring complexity:** customer's regulatory scope may exceed sector pack defaults. Mitigation: Verixa Customer Success engineer paired with customer compliance for first 4 weeks.
- **Reviewer model fit:** customer's workflow may need different reviewer model mix than Phase 0 defaults. Mitigation: model registry supports per-workflow reviewer configuration; mixed model sizes per workload.
- **Joint test plan disagreements:** customer audit function may have different test expectations than Verixa proposes. Mitigation: success criteria locked at SOW signing, not at end of pilot.

---

## 4. Phase 2 — Enterprise Control Plane

**Window:** Q1 2027 (post-first-pilot success)
**Headline:** Human-in-the-loop, sector compliance packs, full Annex IV-aligned dossier, input-side controls.

### 4.1 Phase 2 deliverables

- **Human Review Console** — full reviewer queue UI with workflow context, evidence panel, decision capture, SLA tracking
- **Approval Matrix Engine** — authority-based role bindings, escalation tree, time-bound approvals, MFA at decision time
- **Full Compliance Dossier Generator** — all four pack types (per-decision, per-workflow, Annex IV, Article 72) with full PDF rendering
- **Contradiction Detector** — cross-step reasoning contradiction detection
- **Hallucination Risk Engine** — unsupported-claim and unverified-assertion scoring
- **Sector compliance packs** — financial services (FCA + PRA + EBA), healthcare (MHRA + FDA SaMD), public sector (UK + EU member state)
- **Input-side controls** — PII redaction, prompt-injection detection, source-document trust scoring
- **RBAC at full scope** — admin, policy author, reviewer, auditor, viewer roles with OPA-enforced gates
- **First Tier 2 deployments** — convert Phase 1 pilot customers; expand to additional workflows

### 4.2 Phase 2 success criteria

- 5+ Phase 1 pilots converted to Tier 2 Enterprise contracts
- 1+ regulator engagement on Phase 2-customer Annex IV dossier output
- SOC 2 Type I attestation initiated
- Sector compliance packs validated by Big 4 advisor for at least 2 sectors

---

## 5. Phase 3 — Sovereign Runtime

**Window:** Q2–Q3 2027
**Headline:** Production-grade sovereign deployment for regulated sectors, ISO 27001 / ISO 42001 certifications, drift monitoring.

### 5.1 Phase 3 deliverables

- **Sovereign Runtime hardening** — air-gap-capable deployment patterns, hardware HSM integration option, customer-controlled-key-only mode
- **Model Drift Monitor** — primary model drift detection, reviewer model drift detection, statistical-baseline-against-history
- **Sidecar / service-mesh integration mode** — Istio + Cilium integration patterns; customer-mesh-agnostic interface
- **SOC 2 Type II attestation**
- **ISO 27001 certification**
- **ISO/IEC 42001 certification** (AI Management Systems — Verixa dogfoods its own product to maintain conformance)
- **Tier 3 Sovereign Managed deployments** — first customers on Verixa-operated dedicated tenancy on AMD Developer Cloud

### 5.2 Phase 3 success criteria

- 3+ Tier 3 Sovereign Managed deployments in production
- ISO 42001 certification achieved (Verixa one of first AI governance vendors with this certification)
- 1+ defence-sector or public-sector reference customer

---

## 6. Phase 4 — Trust Graph + Human Operations

**Window:** Q4 2027
**Headline:** Long-term operational intelligence platform; Trust Graph as moat; managed human review operations.

### 6.1 Phase 4 deliverables

- **Trust Graph at full scope** — Apache AGE on Postgres for default tier; Neo4j integration for very large enterprise customers
- **Trust Graph queries** — agent drift history, workflow failure memory, reviewer effectiveness, supplier trust scoring, escalation heatmaps, AI incident lineage, cross-agent behavioural patterns
- **WET Ops** — managed human review operations service tier; Verixa-operated reviewer pool with regulated-sector training
- **Workflow anomaly detection** — Trust Graph-driven flagging of unusual workflow patterns
- **Reviewer effectiveness dashboards** — Control Plane UI surface for reviewer quality
- **Trust Graph in Compliance Dossier** — operational intelligence summaries in Annex IV / Article 72 packs

### 6.2 Phase 4 success criteria

- 80%+ of Tier 2/3 customers using Trust Graph queries in regulator engagement
- WET Ops adopted by 2+ customers as managed review tier
- Trust Graph data informs at least 1 customer's procurement decision on a third-party AI supplier

---

## 7. Phase 5 — Third-party AI Governance

**Window:** Q1–Q2 2028
**Headline:** Verixa governs third-party AI products (Copilot, Salesforce, ServiceNow, etc.) without internal SaaS introspection; Bench, Hallmark, Forge, Replica modules ship.

### 7.1 Phase 5 deliverables

- **Bench** — model and workflow evaluation harness for use-case-specific selection
- **Hallmark** — model and data provenance attestation with cryptographic verification
- **Forge** — policy authoring studio with natural-language to Rego compilation
- **Replica** — standalone simulation and replay sandbox for pre-deployment stress testing
- **Third-party AI wrappers** — Copilot, Salesforce Einstein, ServiceNow Now Assist, equivalents — governed via API wrappers, event gateways, and browser-side policy enforcement
- **Supplier trust scoring at scale** — Trust Graph supplier nodes with aggregated incident lineage across customers (anonymised)

### 7.2 Phase 5 success criteria

- 3+ customers deploying Verixa as governance for third-party AI products
- Hallmark provenance attestation referenced in at least 1 customer's regulator engagement
- Forge reduces customer policy-authoring time by 50%+ for new workflows

---

## 8. Phase 6 — Federated Trust Mesh

**Window:** Q3–Q4 2028
**Headline:** Cross-organisation attestation, supplier evidence sharing, regulator evidence exchange.

### 8.1 Phase 6 deliverables

- **Mesh** — federated trust network for cross-company attestations
- **Cross-org attestation protocol** — SPIFFE federation extension; cross-tenancy zero-trust trust establishment
- **Supplier evidence sharing** — opt-in supplier-to-customer evidence pack delivery via the Mesh
- **Regulator evidence exchange** — regulator-to-customer evidence query via the Mesh (where regulator participates)

### 8.2 Phase 6 success criteria

- 5+ customers participating in trust mesh
- 1+ regulator pilot using mesh for supervised AI evidence exchange
- Trust mesh becomes a competitive advantage for participating customers in their own markets

---

## 9. Cross-cutting concerns

### 9.1 Engineering practice

- **Test discipline:** pytest 100% backend coverage on hot path; Vitest 100% frontend on key flows; Playwright E2E on canonical scenarios
- **Code review:** every PR reviewed by at least 1 engineer + 1 architect on hot-path changes
- **Documentation:** every public API change accompanied by OpenAPI spec update + changelog entry
- **Security:** threat modelling at every phase gate; dependency scanning weekly; CVE patching SLA 7 days critical / 30 days high / 90 days medium

### 9.2 Customer success

- **Pilot delivery:** 1 Customer Success engineer + 1 Compliance specialist + 1 Architect per pilot
- **Annual review:** every Tier 2+ customer reviewed for usage, incidents, expansion opportunities, roadmap alignment
- **Reference programme:** first cohort of customers in each sector receive reference-discount in exchange for case study + reference call participation

### 9.3 Standards-body and ecosystem engagement

- **AAGATE alignment:** maintain published mapping (this documentation pack); contribute to AAGATE evolution where possible
- **CSA AICM:** maintain extension layer; contribute control mappings to CSA
- **NIST AI RMF:** maintain crosswalk; participate in NIST GenAI Profile evolution
- **ISO 42001:** maintain certification (Phase 3+); participate in ISO/IEC SC 42 standards evolution
- **OWASP AIVSS / Top 10 LLM:** maintain cross-reference; contribute customer-anonymised attack-pattern data

### 9.4 Hiring and team scale

- **Phase 0 (hackathon):** founding team
- **Phase 1 (first pilots):** 8–12 engineers + 2 compliance + 2 customer success
- **Phase 2 (enterprise control plane):** 20–30 engineers + 5 compliance + 5 customer success + 3 sales + 2 marketing
- **Phase 3 (sovereign runtime):** 40–50 across product, engineering, customer success, compliance, sales, marketing, ops, security
- **Phase 4–6 (platform expansion):** 80–150+ depending on customer growth

---

## 10. Phase gate reviews

Every phase transition requires a phase gate review with the following criteria:

- **Capability completeness:** all phase deliverables shipped or explicitly deferred with rationale
- **Customer success metrics:** previous-phase customer commitments met
- **Regulatory and security review:** threat model updated; compliance crosswalk updated; certifications maintained
- **Roadmap commitment:** next-phase commitments validated against customer demand and engineering capacity
- **Pricing and commercial:** pricing structure validated against next-phase capability surface

Phase gates are board-reviewed; major scope changes require board approval.

---

## 11. Open architectural decisions deferred to phase gates

- **Phase 2:** Approval Matrix Engine data model (NIST RBAC vs XACML hierarchical role)
- **Phase 4:** Trust Graph storage choice for very large customers (Apache AGE vs Neo4j vs TigerGraph)
- **Phase 5:** Hallmark provenance protocol (in-tree vs adopt emerging open standard)
- **Phase 6:** Federated mesh protocol (SPIFFE federation extension vs custom vs adopt emerging trust-mesh standard)

Each deferred decision has a designated decision date at the relevant phase gate. The Chief Architect maintains the deferred-decisions register.

---

*This Build Plan is the canonical engineering and delivery roadmap for Verixa. The Pricing & Commercial Model document defines the commercial commitments at each phase. The System Architecture Document defines the architectural surface at each phase. Updates require Engineering Lead + Chief Architect approval and Phase Gate review.*
