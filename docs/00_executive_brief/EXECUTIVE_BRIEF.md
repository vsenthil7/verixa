# Verixa — Executive Brief

> Enterprise AI runtime control plane and trust platform.
> Sovereign-deployable on AMD MI300X.
> Document version: 1.1 · Date: 2026-05-10 · Status: Locked positioning
>
> Change note v1.0 → v1.1 (2026-05-10 03:36 UK): "Built on" section reworded to remove percentage-reuse figure. Hackathon-rule hardening per Hack0017 "originality + MIT-compliant" submission clause. Backup of v1.0 retained at `_backup/EXECUTIVE_BRIEF.md_20260510-0335.md`.

---

## What Verixa is

**Verixa is the enterprise AI runtime control plane and trust platform.** It intercepts, verifies, governs, audits, and replays every governed AI-driven action — and creates the evidence to demonstrate and support how those actions were governed before and after they affect the real world.

It is not a chatbot. It is not an LLM provider. It is not a governance dashboard. It is not an observability tool. It is the **runtime control infrastructure** that sits between an enterprise's AI agents and the systems they act on — allowing, blocking, escalating, and recording every governed action at the moment it happens.

---

## Why now

The EU AI Act's high-risk AI obligations are enforceable from August 2026. Article 9 (risk management), Article 14 (human oversight), Article 15 (accuracy and robustness), Article 72 (post-market monitoring), and Annex IV (technical documentation) all require traceable evidence of how AI-driven decisions were made and governed at runtime. NIST AI RMF (Govern / Map / Measure / Manage) and ISO/IEC 42001 establish the same expectation in the US and globally.

In November 2025 the Cloud Security Alliance published AAGATE — a NIST AI RMF-aligned reference architecture for governing agentic AI at runtime. The architecture is published. The implementation is not: AAGATE's open-source MVP is a Genkit dashboard with mock data, not a production-ready governance platform. There is no commercial vendor in the regulated-enterprise market today that combines runtime execution governance, multi-model independent review, deterministic snapshot replay, and an Annex IV-aligned technical dossier in a sovereign deployment.

AMD's MI300X gives the regulated buyer the missing piece: 192 GB HBM3 on a single accelerator hosts substantial multi-model verifier stacks at full precision, with mixed model sizes tuned to the workload — enough headroom for an independent triad reviewer pattern to run on the customer's own infrastructure without sending sensitive prompts to anyone else's cloud.

The category is opening, the standards are converging, the hardware is here. Verixa is the platform for it.

---

## What Verixa does

Verixa governs AI execution across six dimensions:

- **Intercepts** — sits inline in the execution path. Every governed tool call, agent action, or workflow transition passes through the Verixa Runtime Gateway.
- **Verifies** — independent reviewer models (Triad Review Engine) examine high-risk and policy-flagged actions, with hash-commitment before reveal so reviewers cannot herd.
- **Governs** — Open Policy Agent (OPA) Rego policies enforce regulation-as-code at runtime. Risk Engine scores. Decision Router allows / denies / escalates.
- **Audits** — append-only, tamper-evident hash-chain ledger with Ed25519 signatures. Every governed action is provable, immutable, queryable.
- **Replays** — Replay Vault reconstructs past decisions from snapshots: model version, prompt, tools, retrieved documents, reviewer outputs, final decision. Snapshot fidelity, not bit-exact regeneration of external state.
- **Creates evidence** — Compliance Dossier Generator assembles Annex IV-aligned runtime technical dossiers that support the deployer's Article 72 post-market monitoring obligations. PDF + JSON + signed hash chain.

These six are not bolt-ons. They are the runtime substrate.

---

## Platform shape

Verixa is architected as a full enterprise platform from day one. Twenty-four modules across four module groups:

- **Core Runtime (7):** Runtime Gateway · Tool Call Firewall · Policy Engine · Risk Engine · Decision Router · Audit Ledger · Replay Vault
- **AI Verification (5):** Triad Review Engine · Evidence Validator · Contradiction Detector · Hallucination Risk Engine · Model Drift Monitor
- **Enterprise Control (5):** Human Review Console · Approval Matrix Engine · Compliance Dossier Generator · Trust Graph · Workflow Evidence Store
- **Future Expansion (7):** Bench · Hallmark · Forge · Replica · Mesh · WET Ops · (placeholder for v2 expansion)

The build is phased; the architecture is full-scope from day one. Phase 1 ships the Runtime Governance Core (intercept → policy → risk → triad → audit → replay → basic dossier). Phases 2–6 deliver the Enterprise Control Plane, Sovereign Runtime, Trust Graph + Human Ops, Third-party AI Governance, and Federated Trust Mesh.

Verixa's identity arc traces five phases: runtime governance layer → enterprise AI workflow coordinator → AI execution control plane → operational trust intelligence platform → federated AI trust infrastructure. Each phase compounds the prior. The Trust Graph — long-term operational memory of workflows, agents, models, reviewers, suppliers, incidents — is the operational intelligence moat that turns raw governance logs into organisational knowledge of how AI, humans, and systems behave together.

---

## Who it's for

CIOs, CISOs, and Heads of AI Governance at regulated UK and EU mid-to-large enterprises in financial services, healthcare, public sector, defence, and energy. Their pain is operational, not academic: *they cannot deploy AI agents in production because they cannot prove to their regulator, board, or auditor that those agents are governed at runtime*. Their existing AI-GRC tooling generates reports after the fact. Their existing observability tools watch but cannot intervene. Their existing security guardrails filter prompts but do not govern execution. Verixa is what they install when those approaches are no longer enough.

---

## Differentiation

Verixa competes against six adjacent categories. None of them, individually or combined, do what Verixa does:

- **AI Governance Dashboards** (Credo AI, Holistic AI, Trustible) — risk registers, policy libraries, governance reporting. SaaS-only topology rules them out for FCA/PRA/EBA-regulated firms with the most sensitive AI systems. Verixa governs runtime actions at execution time and produces replayable execution traces, not governance snapshots.
- **AI Observability & Monitoring** (Arize, Langfuse, WhyLabs, Fiddler) — telemetry, performance, error tracking. They watch. Verixa intervenes — block, escalate, allow — based on policy and risk, not only log.
- **AI Security / Guardrails** (Lakera, Protect AI, Robust Intelligence) — prompt filters, jailbreak detection. Input/output focus. Verixa adds execution governance (tool-call firewall, delegation controls, approvals) and long-term trust memory.
- **Workflow / Agent Platforms** (LangChain, CrewAI, Microsoft Copilot Studio) — they build agents. Verixa governs and coordinates the actions those agents try to take — sitting around and in front of the platforms, not replacing them.
- **Cloud AI Governance Suites** (Microsoft Purview AI features, Vertex AI governance, Bedrock guardrails) — provider-centric controls inside one cloud. Verixa is cross-model, cross-cloud, and sovereign — governing workflows that span multiple models, multiple clouds, and on-premises systems including open-weight models on AMD MI300X.
- **SIEM / Audit / Logging** (Splunk, Datadog, CrowdStrike) — generic logs and dashboards. Verixa understands AI decision chains, agent actions, tool calls, approvals, and verifier outputs as first-class entities — semantic to AI workflows, not generic log lines.

Most current AI governance vendors observe after execution rather than govern before it. They focus on models rather than workflows and actions. They generate reports rather than runtime decisions. They manage documentation and risk registers rather than enforce live interception and escalation. Verixa moves governance from static reports into the runtime: it governs execution, not just describes it later.

Verixa aligns with AAGATE's NIST AI RMF / EU AI Act / ISO 42001 control crosswalk and CSA's AI Controls Matrix; the Verixa Regulatory Mapping Matrix extends both rather than replacing them. Internally, every Verixa module maps to its AAGATE-style reference equivalent — Runtime Gateway maps to AAGATE Tool-Gateway Chokepoint, Triad Review extends the Janus Shadow-Monitor Agent pattern from one reviewer to three — preserving standards-body legitimacy under Verixa's externally distinct naming.

---

## Compliance vs operational trust

Compliance unlocks budgets. EU AI Act, sector regulators, and internal AI policy make runtime governance urgent and fundable in 2026.

Operational trust is the long-term platform category. Verixa's enduring value is safe AI execution in critical enterprise workflows, high-fidelity replay and incident reconstruction, and long-term trust memory across the Trust Graph.

**Verixa is not EU AI Act paperwork tooling.** Governance and compliance are the forcing functions; the product category is enterprise AI runtime control and operational trust infrastructure.

---

## Built on

- **Compute:** AMD Instinct MI300X via AMD Developer Cloud or customer-deployed
- **GPU runtime:** ROCm 7.x + PyTorch + Hugging Face Optimum-AMD
- **Inference server:** vLLM-on-ROCm (sponsor-aligned, OpenAI-compatible)
- **Reviewer triad (representative):** Qwen3-72B-Instruct + Llama-3.3-70B-Instruct + DeepSeek-V3 — mixed sizes used in early installs depending on workload
- **Backend:** FastAPI + Python 3.12 + Pydantic v2 + SQLAlchemy 2.0 async
- **Storage:** Postgres 16 + pgvector
- **Policy engine:** Open Policy Agent + Rego (regulation-as-code)
- **Crypto:** SHA-256 hash chain + Ed25519 signing
- **Frontend:** Next.js 14 + React 18 + Tailwind + shadcn/ui
- **Container:** Docker Compose for development; Kubernetes-ready for production
- **Open-source dependencies:** Architecture draws on battle-tested patterns from prior governance work — Auditex (Hack0014; hash-commitment + multi-reviewer cryptographic patterns) and SwarmScout (Hack0015; signed envelope and anchor patterns) — both available as MIT-licensed open-source libraries and integrated as standard dependencies.

---

## Status today

- Architecture locked, full enterprise platform scope, phased build sequence defined
- Phase 1 prototype targeting £150k fixed-fee enterprise pilot for one high-value regulated workflow (8–12 weeks)
- Reference architecture aligned with AAGATE (CSA, Nov 2025) and CSA AI Controls Matrix
- Integration modes: OpenAI-compatible proxy and SDK/decorator wrapper in Phase 1; sidecar / service-mesh integration in Phase 2–3 (using customer's existing Istio / Cilium / Linkerd — Verixa does not ship the mesh)
- Deployment options at maturity: on-premises, private cloud, sovereign managed (Verixa-operated dedicated tenancy), Verixa-hosted SaaS for lower-risk customers
- Pricing model: fixed-fee pilot → enterprise annual licence + usage metering on governed actions, replay runs, and triad volume — not tokens
- Hackathon submission: AMD Developer Hackathon (Hack0017), AI Agents & Agentic Workflows track, demonstrating the Phase 1 runtime core end-to-end on MI300X

---

*Verixa is the platform that lets regulated enterprises let AI agents act — safely, provably, and on their own infrastructure.*
