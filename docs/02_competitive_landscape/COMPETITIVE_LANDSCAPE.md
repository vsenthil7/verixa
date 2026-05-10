# Verixa — Competitive Landscape

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Locked positioning · Audience: Procurement officer, CIO, hackathon judge sniff-test, Big 4 advisor

---

## 1. Category framing

Verixa competes in the emerging category of **Enterprise AI Runtime Control Infrastructure** — also referred to in this document as the **AI Runtime Trust Platform** category.

The category does not yet have a settled name in industry analyst reports. Gartner, Forrester, and IDC have all published 2025–2026 research on adjacent categories (AI Governance, AI TRiSM, AI Observability, Responsible AI tooling), but none of them yet name the runtime execution control category that Verixa occupies. This is intentional positioning on Verixa's part: the category is being shaped, and Verixa is shaping it.

**What this category is:**

- A runtime layer that sits between an enterprise's AI agents and the systems they act on
- Inline interception of every governed AI-driven action — proxy, SDK, sidecar
- Policy enforcement, risk scoring, independent verification, and decision routing at execution time, not after
- Tamper-evident audit ledger and snapshot-based replay of past decisions
- Annex IV-aligned technical dossier generation for regulator and auditor consumption
- Long-term trust memory of how AI, humans, suppliers, and systems behave together

**What this category is not:**

- Not a chatbot, not an LLM provider, not an AI agent platform
- Not a governance dashboard or risk register
- Not an observability or telemetry tool
- Not a generic GRC platform with an AI bolt-on
- Not a SIEM or log aggregator
- Not a model-evaluation harness as a standalone product

The strategic position Verixa occupies is **AI Execution Control Plane** — analogous to how Kubernetes is a container execution control plane, how Istio is a service-mesh control plane, how Okta is an identity control plane. Control planes are infrastructure. They are bought once and become substrate.

This positioning is non-negotiable across all Verixa documentation. It anchors every competitive comparison below.

---

## 2. Why existing AI governance is not enough

Six things characterise the current state of AI governance tooling that the regulated enterprise buyer encounters in 2026.

**Most current vendors observe after execution rather than govern before it.** AI governance dashboards and reporting tools generate retrospective views of model behaviour and compliance status. The regulator's question — "show me what happened on May 3rd at 14:22 and prove it was governed" — requires evidence captured at execution time. Retrospective reports cannot reconstruct what was not captured live.

**They focus on models rather than workflows and actions.** Existing AI-GRC tools assess models for bias, drift, and fairness; they evaluate datasets for representativeness; they manage model cards and risk registers. None of this addresses the actual question regulators are asking in 2026, which is about *agents acting on systems* — tool calls, decisions, escalations, approvals, and the chain of reasoning between them. Workflow-level and action-level governance is structurally absent from the current vendor landscape.

**They generate reports rather than runtime decisions.** A report says what happened. A runtime decision says what is allowed to happen next. Regulated enterprises need both, but the runtime decision capability is what blocks production deployment today. A report cannot block an ungoverned tool call. A report cannot escalate a high-risk decision to a human reviewer in 200 milliseconds. A report cannot trigger a triad of independent reviewers and capture their verdicts before the agent acts.

**They manage documentation and risk registers rather than enforce live interception and escalation.** Documentation is necessary but insufficient. The EU AI Act, NIST AI RMF, and ISO 42001 all require documentation, but they also require operational controls. Annex IV is a *technical* file describing how the system works in operation, not just a policy library describing what should happen.

**They typically do not sit inline in the execution path.** AI-GRC SaaS platforms run alongside the customer's AI workflows, ingesting telemetry through APIs and webhooks. They are observers, not gatekeepers. Verixa's Runtime Gateway sits in the execution path. Every governed tool call passes through it. This is an architectural difference, not a feature difference.

**They cannot be deployed sovereign.** SaaS-only deployment topology is a hard "no" for FCA-, PRA-, EBA-, MoD-, and equivalent EU member state-supervised entities running their most sensitive AI workloads. The buyer cannot send sensitive prompts and operational traces to a vendor's cloud. Existing AI-GRC vendors either cannot offer sovereign deployment or offer it as a non-default, non-priced add-on that does not match the buyer's procurement reality.

**Verixa moves governance from static reports into the runtime: it governs execution, not just describes it later.** This sentence is the category-defining claim, and the rest of this document is the evidence for it.

---

## 3. The six competitor categories

Verixa competes against six adjacent vendor categories. Each category solves part of the regulated enterprise's AI problem; none solve the part Verixa solves; and none combine to deliver what Verixa delivers.

### Category 1: AI Governance Dashboards

**Examples:** Credo AI, Holistic AI, Trustible.

**What they do:** Risk registers, policy libraries, compliance workflows, governance reporting dashboards, model cards, vendor questionnaires, fairness and bias evaluation, EU AI Act readiness assessments. Largely workflow-and-documentation tools wrapped around a SaaS platform that ingests model and dataset metadata.

**Where they fit:** AI governance program management, compliance readiness reporting, board-level AI risk visibility.

**Where they fail the regulated buyer:**
- SaaS-only deployment topology rules them out for sovereign-data customers
- They observe and report; they do not govern at execution time
- Workflow-level governance (the actual agent action chain) is not their primary scope
- Annex IV technical documentation generation is partial — they cover the policy and risk-register sections but not the operational evidence that Annex IV requires
- No deterministic replay capability
- No multi-model independent review

**Verixa's difference:**
- Verixa governs runtime actions at execution time
- Verixa produces replayable execution traces, not governance snapshots
- Verixa runs sovereign on the customer's MI300X — no prompts or operational data leave the customer's trust boundary
- Verixa's Compliance Dossier Generator produces the Annex IV-aligned runtime technical dossier these tools cannot produce because they were not in the execution path

**Competitive narrative:** Credo / Holistic / Trustible are good at the AI governance program management layer. They are not the runtime governance layer. Verixa coexists with them or replaces their compliance modules; the runtime substrate is structurally absent from their architecture.

### Category 2: AI Observability & Monitoring

**Examples:** Arize, Langfuse, WhyLabs, Fiddler.

**What they do:** Prompt and response telemetry, latency and error tracking, model performance metrics, drift detection, evaluation harnesses, analytics dashboards. Strong at production AI operations visibility for ML/MLOps teams.

**Where they fit:** ML/MLOps observability, model performance optimisation, prompt engineering iteration, post-deployment monitoring.

**Where they fail the regulated buyer:**
- They watch; they do not intervene. Observability tools cannot block, cannot escalate, cannot route to human approval
- They are designed for ML engineering teams, not for compliance, legal, audit, and risk functions
- No policy-as-code enforcement
- No multi-model independent review
- No Annex IV-aligned dossier generation
- Most are SaaS-only; sovereign deployment varies

**Verixa's difference:**
- Verixa intervenes — block, escalate, allow — based on policy and risk, not only log
- Verixa's Replay Vault provides snapshot-based reconstruction beyond what observability tools' generic telemetry retention provides
- Verixa's audit ledger is hash-chained and signed; observability tools' logs are typically not cryptographically tamper-evident
- Verixa is a control plane buyer (CISO, Head of AI Governance) artefact, not an MLOps tool

**Competitive narrative:** Observability tools are complementary, not competitive. Most regulated enterprises will run both Verixa (governance) and an observability tool (engineering) in production. Verixa wins the governance budget; observability tools win the engineering budget.

### Category 3: AI Security / Guardrails

**Examples:** Lakera, Protect AI, Robust Intelligence (Cisco-acquired), HiddenLayer.

**What they do:** Prompt injection detection, jailbreak filtering, PII redaction, model vulnerability scanning, AI red-teaming, runtime input/output guardrails. Strong at the AI-specific cyber-security threat surface.

**Where they fit:** AI security posture, model vulnerability assessment, input/output safety filtering, AI red-team operations.

**Where they fail the regulated buyer:**
- Input/output focus; not action-side execution governance
- No tool-call firewall, no delegation controls, no approval matrix
- No deterministic replay
- No long-term trust memory
- No Annex IV-aligned dossier
- Often deployed as model wrappers rather than enterprise control planes

**Verixa's difference:**
- Verixa includes execution governance (Tool Call Firewall, Decision Router, Approval Matrix Engine) that input/output guardrails do not address
- Verixa's input-side guardrails (Phase 2) cover PII redaction and prompt-injection detection alongside its action-side governance
- Verixa adds long-term trust memory (Trust Graph) that turns incidents into operational intelligence rather than alerts that fade
- Verixa is a runtime control plane, not a model security wrapper

**Competitive narrative:** AI security vendors will increasingly partner with or be absorbed by larger control planes (Cisco/Robust Intelligence is the precedent). Verixa is positioned to integrate AI security primitives — its own Phase 2 input controls draw on this category's pattern library — but the runtime execution control plane is structurally above the input/output guardrail layer.

### Category 4: Workflow / Agent Platforms

**Examples:** LangChain (LangGraph, LangSmith), CrewAI, Microsoft Copilot Studio, AutoGen, Mistral Le Chat for Enterprise, Anthropic Claude Agent SDK.

**What they do:** Build, orchestrate, and run AI agents. Workflow definition, prompt management, tool integration, multi-agent coordination, agent memory, retrieval-augmented generation. The "build" layer of agentic AI.

**Where they fit:** Engineering teams building AI agents and workflows for the enterprise.

**Where they fail the regulated buyer:**
- They build the agents; they do not govern them
- Built-in observability and tracing (e.g. LangSmith) is engineering telemetry, not regulatory evidence
- Multi-tenant SaaS topology in many cases
- No policy-as-code enforcement layer at runtime
- No multi-model independent review
- No Annex IV-aligned dossier
- Compliance and audit functions are not the buyer; engineering is

**Verixa's difference:**
- Verixa governs and coordinates the actions agents try to take, sitting around and in front of these platforms rather than competing with them
- Verixa's Runtime Gateway accepts traffic from any agent platform via OpenAI-compatible proxy, SDK decorators, or service mesh sidecar
- Verixa's evidence and replay artefacts are regulator-grade, not engineering-grade
- Verixa is the infrastructure these platforms run governed against

**Competitive narrative:** Strongly complementary. Customers will build agents on LangChain or Copilot Studio and govern those agents through Verixa. Verixa's go-to-market includes integration partnerships with the leading agent platforms — these are channel relationships, not zero-sum competition.

### Category 5: Cloud AI Governance Suites

**Examples:** Microsoft Purview AI features, Microsoft Defender for AI, Google Vertex AI governance, AWS Bedrock guardrails and Amazon Q governance, IBM watsonx.governance.

**What they do:** AI governance, guardrails, and audit features within their respective cloud and AI provider stacks. Provider-centric controls tightly integrated with the provider's identity, telemetry, key management, and compliance frameworks.

**Where they fit:** Customers deeply committed to one cloud provider's AI stack who want governance integrated with that provider's existing security and compliance controls.

**Where they fail the regulated buyer:**
- Provider-centric — they govern what runs on *their* cloud, *their* models, *their* services
- Cross-cloud and on-premises governance is partial or absent
- Open-weight models on AMD MI300X are out of their primary scope
- Sovereign deployment outside the provider's cloud is not their model
- Annex IV technical dossier output ranges from partial to absent
- Customers using multiple providers face fragmented governance

**Verixa's difference:**
- Verixa is cross-model, cross-cloud, and sovereign — governing workflows that span multiple models, multiple clouds, and on-premises systems
- Verixa governs open-weight models on AMD MI300X, which provider governance suites do not
- Verixa's identity is platform-independent; the customer's governance is owned by the customer, not by their cloud provider

**Competitive narrative:** This is the category most likely to compete head-on for procurement budget over time. Microsoft Purview, in particular, has the distribution to be the default. Verixa wins on (a) cross-cloud / cross-model scope, (b) sovereign deployment, (c) regulated-sector specificity, (d) AAGATE alignment, (e) avoiding lock-in to one cloud provider's AI stack. Verixa loses where the customer is fully committed to one cloud and wants the operational simplicity of native integration.

### Category 6: SIEM / Audit / Logging

**Examples:** Splunk, Datadog, CrowdStrike, Elastic Security, Microsoft Sentinel.

**What they do:** Ingest generic logs, security events, application telemetry. Provide search, alerting, dashboards, and integrations. The general-purpose enterprise audit and security data layer.

**Where they fit:** Enterprise SIEM, security operations centre tooling, application observability at scale, generic compliance log retention.

**Where they fail the regulated buyer:**
- Generic logs, not AI-semantic logs. They do not understand AI workflow instances, agent actions, tool calls, approvals, verifier outputs, or replay snapshots as first-class entities
- They are passive ingest; they do not govern at execution time
- Annex IV-aligned dossier output is not in scope
- The data model is event-oriented, not decision-oriented

**Verixa's difference:**
- Verixa's Audit Ledger and Replay Vault are AI-workflow-semantic; the data model is built around governed actions, decisions, and reviewer outputs
- Verixa's Compliance Dossier Generator emits Annex IV-aligned output; SIEM dashboards do not
- Verixa is the source of AI-workflow-specific evidence that SIEM systems can ingest as upstream data

**Competitive narrative:** Strongly complementary. Verixa's Audit Ledger can forward to Splunk, Datadog, or Sentinel for the customer's enterprise-wide security data lake. Verixa is the AI-specific source of truth; SIEM is the enterprise-wide consolidation.

---

## 4. Adjacent reference: AAGATE and the standards-body coalition

AAGATE deserves a separate mention because of its role as the most-cited reference architecture rather than as a commercial competitor.

**What AAGATE is:** A NIST AI RMF-aligned reference architecture for governing agentic AI at runtime, published in November 2025 by the Cloud Security Alliance with authors who sit inside NIST AI RMF, OWASP AIVSS, and CSA itself. The paper specifies eight components, seven continuous control loops, and a complete crosswalk to EU AI Act, NIST AI RMF, and ISO 42001. The MVP is an open-source Genkit-based dashboard with mock data, hosted on GitHub.

**What AAGATE is not:** Not a commercial product. Not a deployed implementation. Not a vendor in the procurement set.

**Why AAGATE matters for Verixa's competitive positioning:**
- AAGATE is the architectural artefact Big 4 advisors and enterprise auditors will increasingly point at when asking "what does good look like?" Verixa explicitly aligns with AAGATE rather than competing with it
- AAGATE leaves four explicit gaps that Verixa fills: sovereign on-premises inference, multi-model triad review (vs single-model Janus mirror), deterministic snapshot replay, regulator-ready Annex IV-aligned technical dossier
- Verixa's internal architecture maps every Verixa module to its AAGATE-style reference equivalent, preserving standards-body legitimacy under externally distinct Verixa naming
- No commercial AI-GRC vendor in categories 1–5 above currently references AAGATE, claims AAGATE alignment, or fills AAGATE's named gaps. This is white space

**The strategic move:** Verixa positions as "the sovereign-AMD enterprise implementation of the AAGATE-aligned runtime governance architecture, plus the four extensions (sovereign inference, triad, replay, dossier) the reference architecture does not specify." This is a much stronger story than "yet another AI governance vendor."

---

## 5. Feature-by-feature matrix

This matrix compares Verixa against one representative vendor from each of the six competitor categories (plus AAGATE as reference architecture). For categories with multiple major players, the representative is the most-likely-encountered-in-procurement vendor in regulated UK/EU enterprise.

Symbols: **✅** = does this; **⚠️** = does this partially; **❌** = does not do this; **n/a** = not applicable to that category.

| Capability | Verixa | Credo AI (Cat 1) | Arize (Cat 2) | Lakera (Cat 3) | LangChain (Cat 4) | MS Purview AI (Cat 5) | Splunk (Cat 6) | AAGATE (ref arch) |
|---|---|---|---|---|---|---|---|---|
| Runtime tool-call interception | ✅ | ❌ | ❌ | ⚠️ I/O only | ❌ builds tools | ⚠️ within MS stack | ❌ | ✅ specified |
| Sovereign on-premises deployment | ✅ | ❌ SaaS only | ⚠️ limited | ⚠️ varies | ❌ | ❌ Azure-only | ✅ | ✅ specified |
| Cross-model + cross-cloud governance | ✅ | ⚠️ reporting only | ⚠️ telemetry only | ⚠️ I/O only | n/a builder | ❌ Microsoft-centric | n/a generic | ✅ specified |
| Multi-model independent review (Triad) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ single Janus mirror |
| Hash-commitment before reveal | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Deterministic snapshot replay | ✅ | ❌ | ⚠️ trace replay only | ❌ | ❌ | ❌ | ❌ | ⚠️ specified, not implemented |
| Append-only signed audit ledger | ✅ Ed25519 + hash chain | ⚠️ logs, not signed | ⚠️ logs, not signed | ❌ | ❌ | ⚠️ Microsoft-stack-only | ⚠️ generic logs | ✅ specified |
| OPA + Rego regulation-as-code engine | ✅ | ⚠️ policy library, not OPA | ❌ | ❌ | ❌ | ⚠️ Microsoft policy stack | ❌ | ✅ specified |
| Annex IV-aligned technical dossier output | ✅ | ⚠️ partial coverage | ❌ | ❌ | ❌ | ⚠️ Microsoft-stack-only | ❌ | ⚠️ specified, not implemented |
| Article 72 post-market monitoring evidence | ✅ | ⚠️ reporting only | ⚠️ telemetry only | ❌ | ❌ | ⚠️ within MS stack | ⚠️ generic | ✅ specified |
| NIST AI RMF + ISO 42001 + EU AI Act mapping | ✅ extends CSA AICM + AAGATE | ✅ mapping libraries | ❌ | ❌ | ❌ | ⚠️ Microsoft-only mapping | ❌ | ✅ specified |
| Open-source policy template library | ✅ Verixa public + commercial packs | ⚠️ proprietary library | ❌ | ❌ | ❌ | ⚠️ Microsoft-specific | ❌ | ⚠️ described, not shipped |
| Three integration modes (proxy / SDK / sidecar) | ✅ all 3 phased | ⚠️ APIs only | ⚠️ SDK only | ⚠️ SDK + proxy | n/a builder | ⚠️ within Azure | n/a generic | ✅ all specified |
| GPU-native sovereign inference (AMD ROCm) | ✅ | ❌ | ❌ | ❌ | ❌ builds on top | ❌ Azure GPU only | ❌ | ❌ not specified |
| Triad Review hardware fit on single accelerator | ✅ MI300X 192GB | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| Hallucination Risk Engine (Phase 2) | ✅ | ❌ | ⚠️ basic eval | ⚠️ output filter | ❌ | ❌ | ❌ | ❌ |
| Contradiction Detector (Phase 2) | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Model Drift Monitor (Phase 3) | ✅ | ⚠️ reporting only | ✅ ML-engineer focus | ❌ | ❌ | ⚠️ within MS stack | ❌ | ⚠️ specified |
| Trust Graph — long-term operational memory | ✅ Phase 4 | ❌ | ⚠️ telemetry retention | ❌ | ❌ | ❌ | ⚠️ generic logs | ❌ |
| Reviewer effectiveness tracking | ✅ Phase 4 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Supplier trust scoring (3rd-party AI) | ✅ Phase 4–5 | ⚠️ vendor questionnaires | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Third-party AI governance (Copilot, Salesforce, ServiceNow) | ✅ Phase 5 wrappers | ⚠️ via questionnaires | ❌ | ❌ | ❌ | ✅ Microsoft only | ❌ | ❌ |
| Federated trust mesh (cross-company attestation) | ✅ Phase 6 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Sector-aligned retention tiers (hot / warm / cold) | ✅ | ⚠️ tier 1 only | ⚠️ tier 1 only | ⚠️ tier 1 only | n/a | ⚠️ Azure-tier-only | ✅ generic tiers | ⚠️ specified |
| Approval Matrix (authority-based human-in-the-loop) | ✅ Phase 2 | ⚠️ workflow tasks | ❌ | ❌ | ❌ | ⚠️ Microsoft Approvals | ❌ | ⚠️ specified |
| AAGATE alignment (named control mapping) | ✅ explicit appendix | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | n/a (is AAGATE) |

**Reading the matrix:** No competitor has more than ~30% of Verixa's capability surface, and no two competitors combined cover the runtime + multi-model verification + replay + dossier + sovereign + cross-cloud combination. The full-platform scope itself is the differentiator. Even where individual cells show ⚠️ or partial parity, the combination across the matrix is uniquely Verixa's.

---

## 6. Strategic battlefield

Verixa fights on six fronts simultaneously. Each front has a different competitive dynamic and a different defensive posture.

### Front 1: AI governance vendors (Credo AI, Holistic AI, Trustible)

Verixa's best-equipped opponents on the *governance* dimension. They have customer references in regulated sectors, mature governance program management, and existing relationships with the buyer (Head of AI Governance). They will counter-position Verixa as "narrow runtime tooling that doesn't cover the full governance program."

**Verixa's defence:** "Their governance is reporting; ours is enforcement. Their deployment is SaaS; ours is sovereign. Their dossier is partial; ours is Annex IV-aligned and replayable. We coexist with their program management or replace it with our control plane plus the customer's existing GRC stack."

### Front 2: AI observability vendors (Arize, Langfuse, WhyLabs, Fiddler)

Mostly complementary. They will sell to MLOps and ML engineering. Verixa sells to CISO and Head of AI Governance. Procurement budgets are different; technical buyers are different.

**Verixa's defence:** "We're the governance and audit substrate; they're the engineering observability substrate. Most regulated enterprises will run both."

### Front 3: AI security / guardrail vendors (Lakera, Protect AI, Robust Intelligence)

Increasingly complementary as input/output security primitives get absorbed into broader control planes. The Cisco / Robust Intelligence acquisition is the precedent. Verixa will likely partner-with-or-absorb this layer over time.

**Verixa's defence:** "Their guardrails secure the model; we govern the agent's actions and decisions. We integrate input-side primitives in Phase 2; the runtime control plane is structurally above the prompt-filter layer."

### Front 4: Agent platforms (LangChain, CrewAI, Copilot Studio)

Strongly complementary. Channel partnerships are the win condition. Verixa accepts traffic from any agent platform via proxy, SDK, or sidecar. Verixa's Runtime Gateway is platform-agnostic by design.

**Verixa's defence:** "They build the agents. We govern them. Most enterprise customers will build on LangChain or Copilot Studio and govern through Verixa."

### Front 5: Cloud AI governance suites (Microsoft Purview, Vertex AI governance, Bedrock guardrails)

The hardest competitive front. These vendors have distribution, existing CISO relationships, and the operational simplicity of native cloud integration. Microsoft in particular will be the default for many UK and EU enterprises.

**Verixa's defence:** "We are cross-cloud, cross-model, and sovereign. We govern open-weight models on AMD MI300X — which their suites do not. We are governance the customer owns, not governance owned by the customer's cloud provider. For multi-cloud and sovereign-data customers, we are not negotiable."

This is the strategic battle that defines Verixa's long-term ceiling. The defence is structural: open-weight, cross-cloud, sovereign. As long as those three remain Verixa's design principles, hyperscaler governance suites cannot eat the regulated UK/EU enterprise market.

### Front 6: SIEM / audit / logging vendors (Splunk, Datadog, CrowdStrike, Sentinel)

Complementary. Verixa is the AI-specific source of truth; SIEM is the enterprise-wide consolidation. Forward Verixa's audit ledger to the customer's existing SIEM and the customer gets both.

**Verixa's defence:** "Our data model is AI-semantic. Theirs is generic. They are the downstream consumer of our evidence; they are not a substitute for it."

---

## 7. Verixa's white space — what no competitor in the matrix does

Three capabilities are uniquely Verixa's in the 2026 market:

**Multi-model independent review with hash-commitment before reveal (Triad).** No commercial vendor in any of the six categories implements three independent reviewer models with cryptographic hash-commitment before any reviewer can see the others' verdicts. The pattern is structurally absent from observability tools (they don't run reviewers at all), governance dashboards (they don't run inference), security guardrails (single-model filters at most), agent platforms (they build the agents being reviewed), cloud governance suites (single-provider model bias), and SIEM tools (out of scope). AAGATE specifies a single Janus Shadow Monitor; Verixa extends it to three independent model families with cryptographic non-collusion guarantees.

**Deterministic snapshot-based replay with Annex IV-aligned dossier output.** Observability tools have trace retention but no Annex IV-aligned reconstruction. Governance dashboards have policy libraries but no replay. SIEM has logs but no AI semantics. Verixa's Replay Vault is the only commercial implementation in the 2026 market that lets a regulated enterprise reconstruct a specific past decision and emit the regulator-acceptable technical dossier on demand.

**Long-term Trust Graph as an operational intelligence platform.** The Trust Graph (Phase 4+) captures workflow failure memory, agent drift history, supplier trust scoring, reviewer effectiveness, escalation heatmaps, AI incident lineage, and cross-agent behavioural patterns in a queryable, persistent graph. No competitor in the matrix offers this combination. By Phase 4 the Trust Graph is the artefact the customer cannot replace, cannot rebuild from logs, and cannot get from any other vendor in the category. This is the operational intelligence moat that compounds with every governed action.

These three together are the Verixa wedge. Customers buy Verixa for the runtime control plane; they stay with Verixa because of the Trust Graph.

---

## 8. Where Verixa loses today

Honest accounting of the deficit. Verixa is a new entrant in 2026 against vendors with five-to-fifteen-year head starts in adjacent markets. Six structural disadvantages:

**Feature breadth on adjacent capabilities.** Credo AI has more mature workflow tools, vendor questionnaires, and pre-built bias evaluation suites. Microsoft Purview has deeper integration with the customer's existing identity and security stack. Splunk has the enterprise-wide log aggregation and search capability Verixa will never have at the same scale. Where the customer needs depth in those adjacent capabilities, Verixa does not compete on feature breadth.

**Brand and category recognition.** Gartner, Forrester, and IDC have not yet named the AI Runtime Trust Platform category. Procurement officers at large enterprises will look for vendors in named Magic Quadrants and Wave reports. Verixa is creating the category; the analyst recognition lag is a real procurement friction in 2026.

**Existing integrations and connectors.** Microsoft Purview, ServiceNow GRC, and Splunk have hundreds of pre-built integrations with the customer's existing tooling. Verixa's integration surface in 2026 is the OpenAI-compatible proxy, the SDK, the sidecar, and the audit-ledger forwarders. Fewer surfaces means more bespoke integration work in early customer deployments.

**Sales motion and field presence.** AI-GRC vendors have built named-account sales teams in regulated sectors. Cloud governance suites ride the hyperscaler's enterprise sales motion. Verixa's go-to-market in 2026 is hackathon-anchored credibility, AAGATE alignment, and reference customers — not yet a 50-strong field sales team. Procurement cycles favour the vendor with the established field presence.

**Customer references.** Verixa starts with zero production references. Big regulated enterprises buy from vendors with peer references in the same sector. The first cohort of pilot customers (£150k pilots, 8–12 weeks) is the path to references; until that cohort exists, Verixa will lose deals where the buyer cannot get a peer reference call.

**Operational maturity.** SLAs, incident response runbooks, 24/7 support, sovereign deployment SREs in customer time zones, regulated-sector support certifications — the operational scaffolding around the product takes time to build. Verixa in 2026 is a Phase 1 prototype with a defined operational roadmap; the operational maturity will arrive in Phase 2 and Phase 3 deployments, not at Phase 1 hand-off.

The 6-phase platform roadmap explicitly addresses each of these deficits:
- Phase 2 builds the workflow dashboard, approval matrix, and full Compliance Dossier — closing the feature breadth gap on the governance dimension
- Phase 3 delivers the Sovereign Runtime, sidecar integration, and operational maturity scaffolding for regulated production deployments
- Phase 4 delivers Trust Graph and WET Ops — turning the deficit on operational maturity into a moat
- Phase 5 delivers third-party AI governance wrappers, expanding integration breadth materially
- Phase 6 delivers federated trust mesh — turning brand and reference deficit into network effect

The deficit is real. The plan to close it is concrete. The story to the regulated enterprise buyer is "we are building the category. Be in the first cohort. The reference value compounds."

---

## 9. Category positioning conclusion

Verixa is the **enterprise AI runtime control plane and trust platform** — a category position, not a feature description.

Control planes are infrastructure. They are bought once and become substrate. They compound in value with every workflow they govern, every reviewer decision they capture, every incident they reconstruct. The Verixa Trust Graph turns governance logs into organisational memory. The Verixa Runtime Gateway turns ungoverned AI deployments into governed ones. The Verixa Compliance Dossier Generator turns regulator visits from existential risk events into routine evidence handovers.

In 2026 the category is being created. Verixa is creating it. The competitive landscape above is a snapshot of how the category is differentiated against adjacent vendor types in 2026. By 2028, the category will have a Gartner name, a Forrester Wave, an IDC MarketScape, and a settled vendor set. By 2030, the category will be infrastructure — the way Kubernetes is infrastructure, the way Okta is infrastructure, the way Splunk is infrastructure.

Verixa is built to be the vendor in that category in 2030. The phased build is the path; the full architecture from day 1 is the proof; the regulated enterprise pilot in 2026 is the start.

---

*This Competitive Landscape document is a companion to the Product Vision and Executive Brief. It extends section 7 of the Product Vision into a procurement-grade competitive analysis. The matrix is updated quarterly as the competitive landscape shifts.*
