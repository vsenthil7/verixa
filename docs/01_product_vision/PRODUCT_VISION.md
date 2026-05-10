# Verixa — Product Vision Document

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Locked positioning · Audience: Strategic buyer, investor, advisory board

---

## 1. Vision statement

**Verixa is the enterprise AI runtime control plane and trust platform that intercepts, verifies, governs, audits, replays, and creates evidence to demonstrate and support AI-driven actions before and after they affect the real world.**

Our vision is a world where regulated enterprises can let AI agents act on their most critical workflows with the same operational confidence they have in their human staff: every governed action policy-checked at the moment it happens, every high-risk decision independently reviewed, every outcome reconstructable on demand, every regulator question answerable from primary evidence rather than reconstructed narrative.

Verixa is built for the moment in 2026 when "we use AI" stops being a strategic talking point and becomes an operational risk that must be governed, evidenced, and proven safe — at the speed of execution, not the speed of paperwork.

---

## 2. Problem — why regulated enterprises cannot deploy AI agents at scale today

Regulated enterprises in financial services, healthcare, public sector, defence, and energy sit on a contradiction. Their boards demand AI velocity. Their regulators demand AI traceability. Their existing tooling delivers neither.

Walk through what happens when a regulator, internal auditor, or board risk committee asks the question they will inevitably ask: *"On May 3rd at 14:22, your AI agent took this action that affected this customer. Show me what the model saw, how it reasoned, what policy it was checked against, who approved it, and what evidence you have that this was the right decision."*

In most enterprises today the answer is some combination of:

- **Logs are partial.** Generic application logs captured the API call and response, but not the prompt, not the retrieved documents, not the model version, not the tool decisions in between. The reasoning chain is gone.
- **The model itself cannot be re-run identically.** The provider has updated the model. Your prompt template has changed. Your retrieval index has shifted. There is no way to put the regulator's question back into the system that answered it.
- **There is no independent check.** A single LLM made a single decision. Nothing reviewed it, nothing scored it, nothing flagged risk before it executed.
- **There is no Annex IV-aligned dossier.** Compliance teams have spreadsheets and policy documents. They do not have the technical evidence file the EU AI Act expects.
- **There is no replay.** Even if you had captured everything, there is no system that reconstructs the past decision path on demand for a specific incident.

The operational pain is concrete: regulated enterprises cannot deploy AI agents in production because they cannot prove to their regulator, board, or auditor that those agents are governed at runtime. Pilot deployments stall in legal review. Production systems stay manual. The promised AI velocity does not materialise — not because the technology is too weak, but because the governance substrate is missing.

The market has tried to solve this with adjacent tools. AI governance dashboards generate reports after execution. AI observability tools watch but cannot intervene. AI security tools filter prompts but do not govern execution decisions. GRC platforms manage risk registers and policy documents but do not sit in the execution path. None of them, individually or combined, answer the regulator's question.

Verixa is what you install when those approaches are no longer enough.

---

## 3. Market context — why now

Three structural shifts make 2026 the year the runtime governance category opens.

**Regulatory enforcement is hitting the deployment cycle.** The EU AI Act's high-risk AI obligations are enforceable from August 2026. Article 9 (risk management), Article 13 (transparency), Article 14 (human oversight), Article 15 (accuracy and robustness), Article 72 (post-market monitoring), and Annex IV (technical documentation) all require traceable runtime evidence — not retrospective reports. NIST AI RMF establishes the same expectation in the US through Govern / Map / Measure / Manage functions. ISO/IEC 42001 standardises AI Management Systems globally. UK FCA and PRA have signalled that agentic AI in regulated financial services will be supervised the same way model risk management is supervised today. Compliance teams who were planning for August 2026 in 2024 are operationalising in 2026, and the operational layer they need is not on the market yet.

**The standards-body reference architecture is published but not implemented.** In November 2025 the Cloud Security Alliance, with authors who sit inside NIST AI RMF, OWASP AIVSS, and CSA itself, published AAGATE — a NIST AI RMF-aligned reference architecture for governing agentic AI at runtime. The paper specifies eight components, seven continuous control loops, and a complete crosswalk to EU AI Act, NIST AI RMF, and ISO 42001. The architecture is the most-cited reference enterprise auditors and Big 4 advisors have to point at. The implementation is not: the AAGATE open-source MVP is a Genkit-based dashboard with mock data, not a production-ready governance platform. There is no commercial vendor in the regulated-enterprise market today that combines runtime execution governance, multi-model independent review, deterministic snapshot replay, and an Annex IV-aligned technical dossier in a sovereign deployment. This is white space, not a crowded market.

**Sovereign GPU infrastructure is finally credible for regulated workloads.** AMD's Instinct MI300X, with 192 GB of HBM3 on a single accelerator, makes substantial multi-model verifier stacks viable on the customer's own hardware. ROCm 7.x, vLLM-on-ROCm, Hugging Face Optimum-AMD, and the open-weight model ecosystem (Qwen, Llama, DeepSeek) collectively close the gap that historically forced regulated AI to either run in a hyperscaler cloud (governance compromise) or run quantised on inadequate hardware (capability compromise). A regulated bank or defence ministry can now run independent reviewer models at full reasoning capacity on their own infrastructure for the first time.

The regulatory clock is running. The reference architecture exists. The hardware is here. The vendor that occupies this category in 2026 will be the vendor that defines it for the next decade.

Verixa is built to be that vendor.

---

## 4. Ideal Customer Profile

Verixa is built for regulated UK and EU mid-to-large enterprises in five primary sectors. The ICP is defined by *the operational consequence of getting AI governance wrong*: regulator action, fines, fitness-and-propriety challenges, liability exposure, and the loss of social licence to operate.

### Financial services

- **Tier 1 / Tier 2 retail and commercial banks** — FCA-, PRA-, EBA-, and ECB-supervised. AI in customer onboarding, lending, fraud, AML, customer communications, and increasingly autonomous treasury workflows. Buyer personas: Group CIO, Group CISO, Head of AI Governance, Head of Model Risk Management.
- **Investment banks and asset managers** — MiFID II, SFDR, and increasingly AI-specific supervisory expectations. AI in research, compliance, trade surveillance, and client-facing tools. Buyer personas: COO, Head of Compliance Technology, CTO.
- **Insurers (life, P&C, re)** — claims, underwriting, fraud, customer service. PRA and EIOPA pressure on AI-in-decision. Buyer personas: CIO, Chief Risk Officer, Head of Claims Technology.

### Healthcare

- **NHS Trusts and integrated care systems** — clinical decision support, triage, scheduling, administrative automation. MHRA AI-as-a-medical-device guidance and Article 9 AI Act high-risk classification. Buyer personas: CIO, Caldicott Guardian, Director of Digital, Chief Clinical Information Officer.
- **Private healthcare groups, pharma manufacturers** — clinical, regulatory, manufacturing, and pharmacovigilance AI. Buyer personas: CTO, Head of Pharmacovigilance Technology, Head of Regulatory Affairs.

### Public sector

- **Central government departments** — HMRC, DWP, Home Office, MoJ, equivalents in EU member states. Citizen-facing AI, fraud and compliance AI, decisioning systems. Article 9 AI Act high-risk classification + sector-specific oversight. Buyer personas: CDIO, Chief Digital Officer, Head of AI Strategy, Permanent Secretary on the way to Cabinet Office sign-off.
- **Local government** — citizen services, social care, planning. Same regulatory frame, smaller budgets but real adoption.

### Defence

- **MoD and equivalents, defence prime contractors (BAE, Babcock, Thales, Leonardo, Airbus Defence)** — back-office AI, intelligence analysis, supply chain, and increasingly autonomous decision-support systems. Defence-specific oversight + AI Act Annex III categories. Buyer personas: CIO, Chief Digital Officer, Head of AI Capability, Head of Digital Assurance.

### Energy and critical national infrastructure

- **Utilities, grid operators, water companies, transport operators** — operational AI in grid balancing, demand forecasting, asset management. Ofgem, Ofwat, ORR, sector-specific safety oversight. Buyer personas: CIO, Director of Operational Technology, Chief Safety Officer.

### Common buyer characteristics

Across all five sectors, the Verixa buyer:

- Has board-level AI ambition and board-level risk appetite that contradict
- Has been told by their regulator (formally or informally) that AI deployment requires runtime evidence
- Has a £20–500m+ annual technology budget with AI being a £5–50m line item
- Has tried existing AI-GRC SaaS and found the sovereignty / runtime / evidence gap
- Has internal compliance and audit functions who will be the first reviewers of any AI governance procurement decision
- Cannot send sensitive prompts or operational traces to a vendor's cloud without explicit board approval and a sovereign data agreement most vendors cannot offer

---

## 5. Value proposition — five outcomes Verixa delivers

The 24 modules of the Verixa platform map to five concrete buyer outcomes. The buyer does not buy modules; the buyer buys outcomes.

### Outcome 1: Audit pass

Pass internal audit, external auditor review, and regulator inspection on AI deployments. Regulator says "show me May 3rd at 14:22" — Verixa's Replay Vault and Audit Ledger answer the question from primary evidence in minutes, not weeks. Annex IV-aligned technical dossiers generate on demand. Big 4 auditor accepts the Verixa Compliance Dossier Generator output as substantively equivalent to the technical file format they expect.

*Modules delivering this outcome:* Audit Ledger, Replay Vault, Compliance Dossier Generator, Workflow Evidence Store, Regulatory Mapping Matrix.

### Outcome 2: Fine avoidance and liability containment

EU AI Act administrative fines reach €35M or 7% of global turnover for the most serious violations. UK and sector regulators are scaling. Verixa's runtime governance prevents the violations that drive the largest fines: untraceable high-risk decisions, missing human oversight, unevidenced post-market monitoring, ungoverned third-party AI integrations. Tool Call Firewall blocks ungoverned actions before execution, not after. Approval Matrix Engine enforces the human-in-the-loop the regulation requires.

*Modules delivering this outcome:* Tool Call Firewall, Policy Engine, Risk Engine, Decision Router, Approval Matrix Engine, Human Review Console.

### Outcome 3: Deployment unblocked

The operational pain Verixa solves is "we cannot deploy this in production." Pilot AI workflows that have been stuck in legal-and-compliance review for months exit the holding pattern when the governance substrate is in place. Verixa's three integration modes (proxy, SDK, sidecar) match the customer's deployment topology rather than forcing it. Phase 1 ships in 8–12 weeks against a single high-value workflow; Phase 2+ expands.

*Modules delivering this outcome:* Runtime Gateway (proxy mode), SDK (decorator wrapper), sidecar integration, Workflow Evidence Store.

### Outcome 4: AI velocity with operational confidence

Once Verixa is the substrate, the enterprise can deploy AI agents at the rate of business need rather than the rate of compliance review. Each new workflow inherits the governance, evidence, and replay capability of the platform. The marginal cost of the second, fifth, fiftieth governed AI workflow drops dramatically because the substrate is shared. Agentic workflows that were "too risky to attempt" become "governed and shipped."

*Modules delivering this outcome:* the full platform; specifically the architectural fact that policy, evidence, replay, and review are shared infrastructure rather than per-workflow rebuild.

### Outcome 5: Federated trust posture

In Phase 4–6, the Trust Graph and Federated Trust Mesh transform Verixa from a compliance substrate into an operational intelligence platform. The enterprise gains long-term memory of how its AI, humans, and suppliers actually behave together — which workflows fail, which agents drift, which suppliers are trustworthy, which reviewers add value. Cross-company attestations let the enterprise demonstrate trust posture to its own customers, regulators, and supply-chain partners. This is the moat that compounds over time.

*Modules delivering this outcome:* Trust Graph, Mesh, WET Ops, Model Drift Monitor, Contradiction Detector, Hallucination Risk Engine.

---

## 6. Buyer journey

Verixa's buyer journey has six stages. Each stage has named artefacts that move the buyer to the next stage. The journey from Trigger to Pilot is typically 4–9 months for a regulated enterprise.

### Stage 1: Trigger

Something forces AI governance from "we should think about this" to "we have a deadline." The trigger is usually one of:
- Regulator visit or letter naming AI governance as a supervisory expectation
- Internal Audit finding flagging an AI deployment as ungoverned
- Board risk committee escalation
- A near-miss incident (model hallucination, ungoverned action, customer harm) that surfaces the governance gap
- A planned AI deployment that legal-and-compliance refuses to sign off

Verixa's go-to-market lands on these triggers, not on cold outreach.

### Stage 2: Discovery

Buyer (CIO, CISO, Head of AI Governance) starts mapping the problem. Reads the EU AI Act technical file requirements. Reads NIST AI RMF and AAGATE. Reaches out to peers, advisors, and Big 4 firms. Realises existing AI-GRC SaaS doesn't fit and observability tools don't intervene. Discovers Verixa through standards-body alignment, AAGATE-compatible positioning, regulated-sector reference customers, or AMD partnership channels.

*Verixa artefacts:* this Product Vision document, Executive Brief, AAGATE Mapping Appendix, Regulatory Mapping Matrix.

### Stage 3: Evaluation

Buyer brings Verixa into a formal vendor evaluation. The procurement team requests a System Architecture Document, Threat Model, Security Architecture, Pricing & Commercial Model, and references. Internal auditors review the Compliance Dossier specification. CIO validates the deployment topology against the customer's security architecture (zero-trust, mTLS, sovereign data, etc.). Big 4 advisor reviews the audit defence story.

*Verixa artefacts:* SAD (System Architecture Document), API Specification, Data Model, Threat Model, Security Architecture, Pricing Model, Audit & Evidence Pack Specification.

### Stage 4: Pilot

8–12 week fixed-fee enterprise pilot, £150k, scoped to one high-value regulated workflow. Verixa team deploys Phase 1 runtime governance core in customer environment (sovereign on-prem on customer's MI300X, or sovereign managed tenancy on AMD Developer Cloud). Customer's AI workflow runs through Verixa for the pilot window. Joint success criteria defined upfront: typically (a) audit pass on a synthetic regulator scenario, (b) replay demonstration on a real production decision, (c) Compliance Dossier accepted by customer's external auditor.

*Verixa artefacts:* Pilot Statement of Work, Phase 1 deployment plan, success criteria document, joint test plan.

### Stage 5: Procurement

Successful pilot triggers full procurement. Enterprise annual licence, typical first-year deal £500k–£2m depending on scope. Procurement covers Phase 1 + Phase 2 deployment across multiple workflows + first-year usage commitment. Sovereign deployment topology contractualised. Verixa moves from pilot vendor to strategic infrastructure vendor.

*Verixa artefacts:* Master Services Agreement, Data Processing Agreement, sovereign deployment topology agreement, three-year roadmap commitment.

### Stage 6: Expansion

Year 2 and beyond: customer adds workflows, enables Phase 3+ modules (Trust Graph, Federated Mesh, third-party AI governance), expands to additional business units, joins the Verixa customer trust mesh. Customer becomes a reference for the next cohort of buyers in the same sector. Net Revenue Retention target: 130%+.

*Verixa artefacts:* Roadmap-aligned expansion proposal, peer reference programme, sector advisory board participation.

---

## 7. Differentiation — high-level

Verixa differentiates against six adjacent vendor categories. The full feature-by-feature analysis lives in the Competitive Landscape document; the high-level frame is:

- **AI Governance Dashboards (Credo AI, Holistic AI, Trustible)** govern by reporting after the fact. Verixa governs by enforcing at execution time.
- **AI Observability tools (Arize, Langfuse, WhyLabs, Fiddler)** watch but cannot intervene. Verixa intervenes — block, escalate, allow.
- **AI Security / Guardrails (Lakera, Protect AI, Robust Intelligence)** filter prompts and outputs. Verixa governs the actions agents take in the world.
- **Workflow / Agent Platforms (LangChain, CrewAI, Microsoft Copilot Studio)** build the agents. Verixa governs them, sitting around and in front of the platforms rather than competing with them.
- **Cloud AI Governance Suites (Microsoft Purview, Vertex AI governance, Bedrock guardrails)** govern within one provider's stack. Verixa governs across models, clouds, and sovereign on-prem deployments.
- **SIEM / Audit / Logging (Splunk, Datadog, CrowdStrike)** capture generic logs. Verixa understands AI workflows, agents, and decisions as first-class entities.

Most current AI governance vendors observe after execution rather than govern before it. They focus on models rather than workflows and actions. They generate reports rather than runtime decisions. They manage documentation rather than enforce live interception and escalation. **Verixa moves governance from static reports into the runtime: it governs execution, not just describes it later.**

---

## 8. Identity evolution — five-phase platform arc

Verixa's identity evolves with its capability surface. Each phase is a category position the platform earns on the strength of the prior phase's deployment evidence.

| Phase | Identity | What the platform is recognised as | Evidence base |
|---|---|---|---|
| 1 | **Runtime governance layer** | Gateway + policy + basic verification + replay + ledger + approvals | Pilot wins, Phase 1 deployments, regulator-accepted dossiers |
| 2 | **Enterprise AI workflow coordinator** | Delegation, approvals, escalation trees, input filtering, multi-workflow governance | Cross-workflow deployments, complex enterprise rollouts |
| 3 | **AI execution control plane** | Orchestrates multi-agent workflows across systems, models, and clouds | Sovereign deployments, third-party AI governance, cross-cloud workflow control |
| 4 | **Operational trust intelligence platform** | Trust Graph-driven risk and performance insights across the enterprise's AI estate | Long-term operational memory, drift detection, supplier trust scoring |
| 5 | **Federated AI trust infrastructure** | Cross-org attestations, supplier evidence sharing, regulator evidence exchange | Trust mesh adoption, federated trust posture as competitive advantage for customers |

This arc is not a marketing pivot. Each phase compounds the operational value of the prior phase. By Phase 5 the platform is infrastructure rather than software: the runtime substrate on which an entire economy of governed AI execution sits.

---

## 9. Platform architecture overview — 24 modules in 4 groups

Verixa is architected as a complete enterprise platform from day one. Every module is present in the System Architecture Document with defined module boundaries and interfaces, even if only Phase 1 modules have detailed component-level decomposition initially. The build is phased; the architecture is full-scope from day one.

### Core Runtime (7 modules)

| Module | Purpose |
|---|---|
| Runtime Gateway | Inline interception of every governed AI-driven action — proxy mode, SDK mode, sidecar mode |
| Tool Call Firewall | Allow / block / escalate every governed tool call before execution |
| Policy Engine | OPA + Rego deterministic policy enforcement; regulation-as-code |
| Risk Engine | Score every governed action on policy + behavioural risk dimensions |
| Decision Router | Allow, deny, escalate, or trigger Triad Review based on Risk Engine output |
| Audit Ledger | Append-only tamper-evident hash-chain log with Ed25519 signatures |
| Replay Vault | Snapshot-based reconstruction of past decisions on demand |

### AI Verification (5 modules)

| Module | Purpose |
|---|---|
| Triad Review Engine | Three independent reviewer models with hash-commitment before reveal |
| Evidence Validator | Check claim grounding against retrieved documents and tool outputs |
| Contradiction Detector | Detect contradictions across agent reasoning steps and reviewer outputs |
| Hallucination Risk Engine | Score unsupported claims and unverified assertions |
| Model Drift Monitor | Detect behavioural shifts in primary and reviewer models over time |

### Enterprise Control (5 modules)

| Module | Purpose |
|---|---|
| Human Review Console | Reviewer queue UI with workflow context, evidence panel, decision capture |
| Approval Matrix Engine | Authority-based approval — who can approve what at what risk level |
| Compliance Dossier Generator | Annex IV-aligned technical dossier output (PDF + JSON + signed hash chain) |
| Trust Graph | Long-term operational memory of workflows, agents, models, reviewers, suppliers, incidents |
| Workflow Evidence Store | Per-workflow snapshot context for evidence reconstruction |

### Future Expansion (7 modules architected from day 1, built in later phases)

| Module | Purpose |
|---|---|
| Bench | Model and workflow evaluation harness for use-case-specific selection |
| Hallmark | Model and data provenance attestation with cryptographic verification |
| Forge | Policy authoring studio — natural-language to Rego compilation |
| Replica | Standalone simulation and replay sandbox for pre-deployment stress testing |
| Mesh | Federated trust network for cross-company attestations and supplier evidence |
| WET Ops | Managed human review operations as a service tier |
| (placeholder) | Reserved for v2 platform expansion based on customer demand |

The architectural commitment: every module above is visible in the SAD module diagram from day 1. Phase 1 builds the Core Runtime + Triad Review + Evidence Validator + basic Compliance Dossier + Workflow Evidence Store. Phase 2 builds the Enterprise Control Plane (Human Review Console, Approval Matrix, full Compliance Dossier, plus Contradiction Detector and Hallucination Risk Engine). Phase 3 builds Sovereign Runtime including Model Drift Monitor and sidecar mode. Phase 4 delivers the Trust Graph and WET Ops. Phase 5 delivers Bench, Hallmark, Forge, and Replica plus third-party AI governance wrappers. Phase 6 delivers the Mesh.

---

## 10. Trust Graph — the operational intelligence moat

The Trust Graph is not a feature. It is the long-term operational intelligence moat that distinguishes Verixa from compliance middleware over the platform lifecycle.

The Trust Graph is the persistent, queryable graph of:

- **Workflow instances** — every governed workflow, its history, its outcomes, its failures
- **Agents** — every AI agent governed by Verixa, its model versions, its behavioural fingerprint over time
- **Models** — every primary and reviewer model deployed, its drift trajectory, its incident lineage
- **Human reviewers** — who reviewed what, decision quality over time, override patterns, latency
- **Suppliers** — third-party AI products and data sources, trust posture over time
- **Incidents** — every escalation, override, near-miss, policy breach, and remediation
- **Approvals** — every approval-matrix decision and the authority chain that validated it

The Trust Graph captures dimensions no log file or governance dashboard captures:

- **Workflow failure memory** — which workflows frequently hit policy violations, frequently escalate to humans, frequently produce overrides, and how those patterns evolve as the workflow matures
- **Agent drift history** — when an agent's behaviour shifts (more escalations, more reviewer disagreements, more contradiction detections) before it shows up in operational metrics
- **Supplier trust scoring** — patterns in external AI/SaaS interactions that correlate with incidents or risky behaviour, enabling supplier risk decisions grounded in operational data rather than vendor questionnaires
- **Reviewer effectiveness** — which humans consistently make good overrides, who over-approves, who is overloaded, who catches genuine risk versus who rubber-stamps
- **Escalation heatmaps** — where in the org and which workflows produce the most escalations and incidents, surfacing organisational risk concentration
- **AI incident lineage** — the graph of related incidents, root causes, and remediation over time, turning point incidents into organisational learning
- **Cross-agent behavioural patterns** — emergent behaviours when multiple agents interact or act in sequence, which no per-agent monitoring tool will see

The Trust Graph turns the runtime governance substrate into organisational memory about how AI, humans, and systems behave together. By Phase 4 it is the artefact the buyer cannot replace, cannot rebuild from logs, and cannot get from any other vendor in the category. It compounds in value with every governed action, every reviewer decision, every incident.

This is what makes Verixa a long-term operational intelligence platform rather than a compliance middleware vendor.

---

## 11. Compliance vs operational trust

Compliance unlocks budgets. EU AI Act enforcement from August 2026, sector regulators (FCA, PRA, EBA, MHRA, Ofgem, MoD AI Assurance), and internal AI policy make runtime governance urgent and fundable in 2026. Procurement signs the cheque because the compliance forcing function is real.

Operational trust is the long-term platform category. Verixa's enduring value to the customer is safe AI execution in critical enterprise workflows, high-fidelity replay and incident reconstruction, and long-term trust memory across the Trust Graph. Five years from now the customer will not measure Verixa's value in EU AI Act audit defence — they will measure it in AI velocity, incident reduction, and operational intelligence captured.

**Verixa is not EU AI Act paperwork tooling.** Governance and compliance are the forcing functions. The product category is enterprise AI runtime control and operational trust infrastructure. Internal positioning, sales motion, roadmap investment, and customer-success metrics all anchor on operational trust as the long-term frame, not compliance paperwork.

This positioning is non-negotiable. It is what protects Verixa from being mentally reduced — by the next CIO, the next investor, the next Verixa team member — to "EU AI Act regtech." Regtech is a niche. Operational trust infrastructure is a category.

---

## 12. Why AMD

Verixa's sovereign deployment story is built on AMD because AMD is the only vendor whose hardware, software stack, and ecosystem currently make sovereign multi-model verification economically viable for regulated enterprises.

**Memory capacity at single-accelerator scale.** The Instinct MI300X carries 192 GB of HBM3 on a single accelerator. This is the architectural enabler for substantial multi-model verifier stacks running on customer-owned hardware — the Triad Review Engine, the Evidence Validator, the Contradiction Detector — without the customer's prompts or operational traces ever leaving their trust boundary. Mixed model sizes are used in early installs depending on workload; the specific quantisation and KV-cache strategy is workload-tuned. The architectural point is that single-card multi-model verification is feasible on AMD MI300X in a way it is not on competing accelerators at this price-performance point.

**Open software stack with regulated-deployment fit.** ROCm 7.x is open-source. PyTorch on ROCm runs the same training and inference codepaths as the CUDA ecosystem, without CUDA dependency. Hugging Face Optimum-AMD provides first-class integration with the open-weight model ecosystem (Qwen, Llama, DeepSeek, Mistral). vLLM-on-ROCm provides production-grade serving with OpenAI-compatible APIs. The open-weight model story matters specifically for regulated buyers: open weights mean the model can be deployed inside the customer's trust boundary without vendor lock-in to a closed-model provider.

**AMD Developer Cloud and sovereign tenancy options.** Verixa's deployment topology supports on-premises (customer-owned MI300X), private cloud (customer's existing private cloud with MI300X capacity), sovereign managed (Verixa-operated dedicated tenancy on AMD Developer Cloud), and Verixa-hosted SaaS (lower-risk customers). The AMD Developer Cloud sovereign tenancy story is what enables regulated mid-market customers to deploy Verixa without buying their own MI300X clusters, materially expanding the addressable market.

**Strategic alignment.** AMD's positioning as the open, sovereign-friendly alternative to closed hyperscaler AI infrastructure aligns directly with Verixa's value proposition to regulated enterprises. AMD is not just a compute substrate; AMD is the strategic partner whose go-to-market in regulated UK and EU enterprise mirrors Verixa's. The two stories reinforce each other.

This is not a CUDA-to-ROCm migration story. This is an architecture that is buildable now because AMD's stack reached production-readiness for this exact use case in 2025–2026. Verixa is built on AMD because AMD is the only credible substrate for sovereign multi-model AI governance at enterprise scale today.

---

*This Product Vision is the canonical strategic document for Verixa. The Executive Brief summarises it. The Competitive Landscape extends section 7. The System Architecture Document operationalises sections 8–12. Every downstream artefact in the documentation pack derives from this document.*
