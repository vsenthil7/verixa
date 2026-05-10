# Verixa — System Architecture Document (SAD)

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 architecture locked, full-platform architecture visible · Audience: CTO, Chief Architect, Solution Architect, security architect, Big 4 advisor

---

## 1. Document scope and structure

This System Architecture Document (SAD) describes the Verixa platform architecture using the C4 model (Context → Container → Component → Code), extended with deployment topology, security architecture, scalability and high-availability model, and disaster recovery and replay model.

The architecture is full-platform from day one. The build is phased per the Build Plan. This SAD describes the architecture of the platform at maturity (all six phases delivered). Phase-1-only details are explicitly marked.

---

## 2. C4 Level 1 — System Context

The System Context describes how Verixa fits into the customer's enterprise environment.

```text
                    [Regulator]
                        |
                        | Annex IV-aligned dossier
                        | Article 72 evidence
                        v
   +---------------------------------------------+
   |          Customer Enterprise                 |
   |                                              |
   |  [AI Agent / Workflow]                       |
   |        |                                     |
   |        | governed action                     |
   |        v                                     |
   |  +--------------+      +-----------------+   |
   |  |    VERIXA    |<---->|  Customer GRC,  |   |
   |  | (this system)|      |  SIEM, IAM,     |   |
   |  +--------------+      |  ITSM, Audit    |   |
   |        |               +-----------------+   |
   |        | enforcement                         |
   |        v                                     |
   |  [Tools / APIs / Systems]                    |
   |  (CRM, ERP, banking core, EHR, etc.)         |
   +---------------------------------------------+
                        ^
                        |
                  [Auditor / Big 4]
                  [Internal Audit]
                  [Board Risk Committee]
```

**External actors interacting with Verixa:**

- **AI Agent / Workflow** — the customer's AI agent or workflow that Verixa governs. Sends governed actions through Verixa Runtime Gateway via proxy, SDK, or sidecar mode.
- **Tools / APIs / Systems** — the customer's systems that AI agents act on. Verixa's enforcement decisions allow, deny, or escalate before tool calls reach these systems.
- **Customer GRC, SIEM, IAM, ITSM, Audit systems** — Verixa integrates bidirectionally: ingests policy and identity context from customer systems, forwards audit events and incident records to customer SIEM/audit, raises tickets in customer ITSM for escalations and incidents.
- **Regulator** — receives Annex IV-aligned technical dossiers and Article 72 post-market monitoring evidence on demand or per regulatory cadence.
- **Auditor / Big 4 / Internal Audit / Board Risk Committee** — receives evidence packs, runs replay queries, validates governance posture.

---

## 3. C4 Level 2 — Container View

The Container view decomposes Verixa into the runtime, control, and data containers that together form the platform.

```text
+---------------------------------------------------------------+
|                          VERIXA PLATFORM                       |
|                                                                |
|  +---------------------------+  +------------------------+    |
|  |  RUNTIME CONTAINER         |  |  CONTROL PLANE         |    |
|  |  (FastAPI + vLLM-on-ROCm) |  |  CONTAINER (FastAPI)   |    |
|  |                           |  |                        |    |
|  |  - Runtime Gateway        |  |  - Admin API           |    |
|  |  - Tool Call Firewall     |  |  - Policy Authoring    |    |
|  |  - Policy Engine (OPA)    |  |  - Approval Matrix     |    |
|  |  - Risk Engine            |  |  - Human Review Console|    |
|  |  - Decision Router        |  |  - Trust Graph queries |    |
|  |  - Triad Review Engine    |  |  - Dossier Generator   |    |
|  |  - Evidence Validator     |  +------------------------+    |
|  +---------------------------+              ^                  |
|              |                              |                  |
|              v                              |                  |
|  +---------------------------+              |                  |
|  |  EVIDENCE & STORAGE        |             |                  |
|  |                            |<------------+                  |
|  |  - Audit Ledger (Postgres) |                                |
|  |  - Replay Vault (object    |                                |
|  |    store + Postgres index) |                                |
|  |  - Trust Graph (Postgres   |                                |
|  |    + pgvector + graph ext) |                                |
|  |  - Workflow Evidence Store |                                |
|  +---------------------------+                                 |
|              ^                                                  |
|              |                                                  |
|  +---------------------------+                                  |
|  |  BACKGROUND JOBS           |                                  |
|  |  (Celery + Redis)          |                                  |
|  |                            |                                  |
|  |  - Compliance Dossier      |                                  |
|  |    rendering               |                                  |
|  |  - Model Drift Monitor     |                                  |
|  |  - Retention tier moves    |                                  |
|  |  - Trust Graph rollups     |                                  |
|  +---------------------------+                                  |
|                                                                  |
|  +---------------------------+   +------------------------+    |
|  |  REVIEWER MODELS           |   |  IDENTITY & SECRETS    |    |
|  |  (vLLM-on-ROCm, MI300X)    |   |                        |    |
|  |                            |   |  - Verixa SPIRE/SPIFFE |    |
|  |  - Qwen3-72B-Instruct      |   |  - Vault (HashiCorp or |    |
|  |  - Llama-3.3-70B-Instruct  |   |    customer-deployed)  |    |
|  |  - DeepSeek-V3 (or mixed   |   |  - Customer IAM (OIDC, |    |
|  |    sizes per workload)     |   |    SAML)               |    |
|  +---------------------------+   +------------------------+    |
|                                                                  |
+-----------------------------------------------------------------+
```

**Container responsibilities:**

- **Runtime Container** — the hot path. Every governed action passes through this container. Co-located with the customer's AI workload for low latency. FastAPI front-end, async Python, OPA-Rego embedded for policy decisions, vLLM-on-ROCm for reviewer model inference (Sovereign Verifier mode).
- **Control Plane Container** — the cold path. Admin operations, policy authoring, human review console, dossier generation, Trust Graph queries. Not in the hot path; can run with weaker latency requirements.
- **Evidence & Storage** — Postgres 16 + pgvector + a graph extension (Apache AGE on Postgres, or external Neo4j for very large Trust Graph deployments). Object store for Replay Vault binary artefacts (S3-compatible, MinIO for on-prem).
- **Background Jobs** — Celery + Redis for asynchronous workloads: dossier rendering, drift monitoring, retention-tier movement, Trust Graph rollups.
- **Reviewer Models** — Triad Review and Evidence Validator inference. Runs on customer's MI300X cluster in Sovereign Verifier mode; runs on Verixa-managed cluster in Sovereign Managed and Hosted SaaS tiers.
- **Identity & Secrets** — SPIRE/SPIFFE for Verixa's internal service identity; HashiCorp Vault (or customer-deployed Vault) for secrets; customer IAM via OIDC/SAML for human authentication into the Control Plane.

---

## 4. C4 Level 3 — Component View (Runtime Container detail)

The Runtime Container is the highest-stakes component. Sub-components inside it:

```text
+------------------------------------------------------------------+
|                      RUNTIME CONTAINER                             |
|                                                                    |
|   incoming governed action                                        |
|         |                                                          |
|         v                                                          |
|   +----------------------+                                        |
|   |  Runtime Gateway     |                                        |
|   |  (FastAPI front-end) |                                        |
|   |  - Auth + identity   |                                        |
|   |  - Schema validation |                                        |
|   |  - Request envelope  |                                        |
|   +----------------------+                                        |
|         |                                                          |
|         v                                                          |
|   +----------------------+      +----------------------+          |
|   |  Tool Call Firewall  |----->|  Policy Engine       |          |
|   |  - Allow / deny      |      |  - OPA evaluator     |          |
|   |  - Schema enforce    |      |  - Rego policies     |          |
|   |  - Argument bound    |      |  - Regulation-as-code|          |
|   +----------------------+      +----------------------+          |
|         |                                                          |
|         | (allowed)                                                |
|         v                                                          |
|   +----------------------+                                        |
|   |  Risk Engine         |                                        |
|   |  - Action risk score |                                        |
|   |  - Workflow context  |                                        |
|   |  - Policy flags      |                                        |
|   +----------------------+                                        |
|         |                                                          |
|         v                                                          |
|   +----------------------+      +-------------------------+       |
|   |  Decision Router     |----->|  Triad Review Engine    |       |
|   |  - Thresholds        |      |  (high-risk / flagged)  |       |
|   |  - Sampling logic    |      |  - 3 reviewer models    |       |
|   |  - Human review      |      |  - Hash-commit + reveal |       |
|   |    routing           |      |  - Consensus logic      |       |
|   +----------------------+      +-------------------------+       |
|         |                                  |                       |
|         |       +--------------------------+                       |
|         |       v                                                  |
|         |  +----------------------+                               |
|         |  |  Evidence Validator  |                               |
|         |  |  - Citation grounding|                               |
|         |  |  - Source-pack check |                               |
|         |  +----------------------+                               |
|         |                                                          |
|         v                                                          |
|   +-------------------------+                                      |
|   |  Audit Emit             |                                      |
|   |  - Hash-chain entry     |                                      |
|   |  - Ed25519 sign         |                                      |
|   |  - Snapshot capture for |                                      |
|   |    Replay Vault         |                                      |
|   +-------------------------+                                      |
|         |                                                          |
|         v                                                          |
|   action allowed / denied / escalated                             |
|                                                                    |
+--------------------------------------------------------------------+
```

**Component responsibilities (Runtime Container):**

- **Runtime Gateway** — FastAPI + Pydantic v2. Authenticates the calling agent via SPIFFE identity. Validates the request schema. Wraps the action in a Verixa request envelope with workflow context, agent identity, model identity, and timestamp.
- **Tool Call Firewall** — Validates the tool call against an allow-list of known tool schemas. Enforces argument bounds (e.g. transfer amount ≤ £10,000 for this agent role). Blocks malformed or out-of-scope calls before they reach Policy Engine.
- **Policy Engine** — OPA (Open Policy Agent) runtime evaluating Rego policies. Policies are regulation-as-code: each policy maps to one or more EU AI Act / NIST AI RMF / ISO 42001 / sector-specific control. Evaluation is deterministic and sub-millisecond.
- **Risk Engine** — Scores the action on multiple dimensions: workflow risk classification, agent reputation (from Trust Graph), policy flags, action sensitivity, downstream-system criticality. Output: numeric risk score + risk classification (low / medium / high).
- **Decision Router** — Routes the action based on Risk Engine output and policy flags. Low-risk → allow. Medium-risk → optionally Triad sample, then allow. High-risk → Triad Review required, then route based on triad consensus. Policy-flagged → human review queue. Hard policy breach → block regardless of triad.
- **Triad Review Engine** — Spawns three independent reviewer model invocations on Sovereign Verifier MI300X. Each reviewer receives the same review package (action description, workflow context, source documents). Each commits a hash of its verdict to the Audit Ledger before any reviewer can see the others' verdicts. After all three commit, verdicts are revealed and consensus is computed. Disagreement triggers escalation per policy.
- **Evidence Validator** — For actions involving claims (e.g. agent says "the customer's balance is £500"), validates the claim against source documents and tool outputs. Flags ungrounded or contradicted claims.
- **Audit Emit** — Writes the complete decision record to the Audit Ledger as a hash-chained, Ed25519-signed entry. Captures the snapshot bundle (model version, prompt, retrieved documents, tool inputs and outputs, reviewer verdicts, final decision) to the Replay Vault.

---

## 5. Component View (Control Plane Container detail)

```text
+------------------------------------------------------------------+
|                   CONTROL PLANE CONTAINER                          |
|                                                                    |
|   +-------------------+    +--------------------------+           |
|   |   Admin API       |    |  Policy Authoring        |           |
|   |   (REST + GraphQL)|    |  - Rego editor           |           |
|   |   - Workflow      |    |  - Policy test harness   |           |
|   |     management    |    |  - Compliance pack mgmt  |           |
|   |   - Agent registry|    +--------------------------+           |
|   +-------------------+                                            |
|                                                                    |
|   +-------------------+    +--------------------------+           |
|   |  Approval Matrix  |    |  Human Review Console    |           |
|   |  - Authority      |    |  - Reviewer queue        |           |
|   |    chains         |    |  - Workflow context      |           |
|   |  - Role bindings  |    |  - Evidence panel        |           |
|   |  - Escalation tree|    |  - Decision capture      |           |
|   +-------------------+    +--------------------------+           |
|                                                                    |
|   +-------------------+    +--------------------------+           |
|   |  Trust Graph      |    |  Compliance Dossier      |           |
|   |  Query Service    |    |  Generator               |           |
|   |  - Graph traversal|    |  - Annex IV templates    |           |
|   |  - Drift queries  |    |  - PDF + JSON output     |           |
|   |  - Heatmaps       |    |  - Hash-chain proof      |           |
|   +-------------------+    +--------------------------+           |
|                                                                    |
|   +-------------------+    +--------------------------+           |
|   |  Replay Service   |    |  Reporting & Dashboards  |           |
|   |  - On-demand      |    |  - Operational metrics   |           |
|   |    reconstruction |    |  - Compliance status     |           |
|   |  - What-if replay |    |  - Trust Graph views     |           |
|   +-------------------+    +--------------------------+           |
|                                                                    |
+------------------------------------------------------------------+
```

---

## 6. Data flow — the canonical "governed action" lifecycle

This is the canonical data flow for a single governed action. It is the most important diagram in this document for understanding what Verixa does at runtime.

```text
   [AI Agent]
       |
       | (1) attempts tool call
       v
   [Verixa Runtime Gateway]
       |
       | (2) authenticate agent (SPIFFE ID)
       | (3) validate schema
       | (4) wrap in Verixa envelope
       v
   [Tool Call Firewall]
       |
       | (5) check allow-list, argument bounds
       v
   [Policy Engine — OPA + Rego]
       |
       | (6) evaluate active policies
       | (7) emit policy decision + flags
       v
   [Risk Engine]
       |
       | (8) score action
       | (9) classify risk level
       v
   [Decision Router]
       |
       | (10) route by risk + policy flags
       v
   --------- HIGH-RISK BRANCH ---------
       |
       v
   [Triad Review Engine]
       |
       | (11a) reviewer A receives package, commits hash
       | (11b) reviewer B receives package, commits hash
       | (11c) reviewer C receives package, commits hash
       | (12) all 3 hashes written to Audit Ledger
       | (13) reveal phase: each reviewer publishes verdict
       | (14) consensus computed
       | (15) if disagreement → escalate to Human Review Console
       v
   --------- ALL BRANCHES REJOIN ---------
       |
       v
   [Evidence Validator] (claim-bearing actions)
       |
       v
   [Audit Emit]
       |
       | (16) hash-chain entry
       | (17) Ed25519 signature
       | (18) snapshot bundle to Replay Vault
       | (19) Trust Graph update
       v
   [Decision delivered]
       |
       +-- ALLOW   → tool call proceeds
       +-- DENY    → tool call blocked, agent receives policy violation
       +-- ESCALATE → human review queue, agent receives "pending"
       v
   [Audit Ledger + Replay Vault + Trust Graph]
       (persistent evidence)
```

**Latency budget for the hot path (Phase 1 production target):**

- Steps 1–5 (gateway + firewall): ≤ 5 ms
- Step 6 (policy evaluation): ≤ 10 ms (OPA p99)
- Steps 7–10 (risk + routing): ≤ 5 ms
- Steps 11–15 (triad, when triggered): ≤ 800 ms (parallel inference on MI300X)
- Steps 16–19 (audit emit + snapshot): ≤ 20 ms (async to hot path)

**Total p99 latency for low-risk path (no triad): ≤ 50 ms.**
**Total p99 latency for high-risk path (with triad): ≤ 1000 ms.**

These are Phase 1 targets; Phase 3 deployments will tune to sector-specific SLAs.

---

## 7. Deployment topologies

Verixa supports four deployment topologies, all architected from day 1.

### 7.1 On-premises (customer-owned MI300X)

- Customer provides MI300X cluster on customer-owned hardware
- Verixa runtime + control plane + storage deploy via Kubernetes (Helm charts) or Docker Compose
- Customer-managed networking, identity (OIDC/SAML), key management, backup
- Verixa support via secure remote access or on-site engineer rotation
- Use case: Banks, defence, public sector with strict on-premises mandates

### 7.2 Private cloud

- Customer's existing private cloud (e.g. on hyperscaler with sovereign-region commitment, or private-cloud-as-a-service provider)
- MI300X capacity provisioned in customer's tenant
- Verixa deployed via Kubernetes in customer's cluster
- Customer-managed networking + security; Verixa-managed application layer
- Use case: Enterprise customers with established private-cloud strategy

### 7.3 Sovereign managed (Verixa-operated dedicated tenancy on AMD Developer Cloud)

- Verixa operates a dedicated single-tenant deployment on AMD Developer Cloud
- Customer's data segregated by tenancy; no multi-tenant overlap
- Verixa-managed networking, key management (per-tenant key hierarchy), backup, SRE
- Customer accesses via Verixa Control Plane UI + API
- Use case: Regulated mid-market that wants sovereign deployment without infrastructure ownership

### 7.4 Hosted SaaS (multi-tenant)

- Verixa-hosted multi-tenant deployment on AMD Developer Cloud
- Tenant isolation via logical separation (per-tenant DBs + per-tenant key hierarchy)
- Use case: Lower-risk customers, departmental deployments, mid-market with non-regulated AI workflows

**Across all four topologies, the architecture is identical.** Differences are in operational responsibility, key management hierarchy, and tenancy model — not in code. This matters: code paths are uniform, so security review, audit, and certification done for one topology applies to all four.

---

## 8. Security architecture

### 8.1 Trust boundaries

Three trust boundaries:

- **Tenancy boundary** — between Verixa tenants. Hard isolation in single-tenant deployments (Tiers 1, 2, 3); logical isolation in multi-tenant SaaS (Tier 4).
- **Verixa internal boundary** — between Verixa runtime, control plane, evidence storage, and reviewer models. Zero-trust assumptions; mTLS between containers; SPIFFE service identity.
- **Customer boundary** — between Verixa and the customer's other systems (CRM, ERP, IAM, SIEM, ITSM). Authenticated and audited integrations; no implicit trust.

### 8.2 Identity model

- **Service identity:** SPIFFE / SPIRE for Verixa's internal services. Each container has a SPIFFE ID; mTLS between containers uses SPIFFE-issued certificates.
- **Agent identity:** Customer's AI agents authenticate to the Runtime Gateway via API keys, mTLS client certs, or workload identity (SPIFFE federation in Phase 2+).
- **Human identity:** Customer's IAM via OIDC or SAML for Verixa Control Plane. Role-based access control (RBAC) for admin, policy author, reviewer, auditor roles. Multi-factor authentication required for production environment access.

### 8.3 Key management

- **Audit Ledger signing:** Per-tenant Ed25519 signing key. Signing key rotated quarterly; old keys retained for verification of historical entries.
- **Replay Vault encryption:** Per-tenant AES-256-GCM encryption for snapshot bundles; per-customer-or-per-workflow key hierarchy.
- **Triad commitment:** Per-decision SHA-256 hash for reviewer hash-commitment. No long-lived secret involved in the commit-reveal protocol; the commit is just a hash of (verdict + nonce).
- **Key storage:** HashiCorp Vault in Tier 2/3/4 deployments; customer-deployed Vault in Tier 1 on-prem. AWS KMS / Azure Key Vault / Google Cloud KMS supported as Vault backends in private-cloud topologies.

### 8.4 Zero-trust enforcement

- mTLS between every pair of Verixa containers
- No service is implicitly trusted; every request is authenticated and authorised
- Network segmentation: hot-path runtime is on a separate network from control plane; storage layer is on its own network
- OPA gates not just policy decisions but also internal API access (Verixa dogfoods its own policy engine for its own admin operations)

### 8.5 Threat model summary

The Threat Model document is a separate artefact in this pack. STRIDE analysis covers prompt injection, model tampering, audit-log tampering, replay corruption, key compromise, and the AAGATE-named risk classes (LPCI, QSAF, DIRF, Supply-Chain Blindness). OWASP Top 10 for LLMs is fully cross-referenced.

---

## 9. Scalability and high availability

### 9.1 Scaling dimensions

- **Governed actions per second** — primary scaling metric. Phase 1 target: 100 actions/sec per Runtime Container instance; horizontal scale via additional Runtime Container replicas behind a load balancer.
- **Triad invocations per second** — secondary scaling metric, gated by reviewer model GPU capacity. Phase 1 target: 10 triad invocations/sec per MI300X with mixed-size reviewer models. Scale by adding MI300X capacity.
- **Replay queries per second** — Control Plane scaling. Phase 1 target: 100 concurrent replay queries.
- **Trust Graph queries** — Phase 4+ scaling consideration. Postgres + Apache AGE handles small-to-medium graphs; Neo4j or TigerGraph in dedicated graph-DB tier for very large enterprise customer Trust Graphs.

### 9.2 High availability

- **Active-active runtime** — Runtime Container deployed in at least 3 replicas behind an internal load balancer. Loss of any single replica does not interrupt governance.
- **Postgres with replication** — primary + 2 read replicas. Failover via Patroni or equivalent. RTO 30 seconds, RPO < 1 second.
- **Object store for Replay Vault** — uses underlying object store HA (S3 99.999999999% durability, MinIO with erasure coding for on-prem).
- **Reviewer model availability** — at least 2 MI300X-equivalent instances per tenant for Tier 2+. Loss of one MI300X falls back to two-of-three triad with policy-defined consensus rules; loss of two falls back to single-reviewer with high-risk decisions auto-escalated to human review.

### 9.3 Performance hot path

The Runtime Container's hot path is engineered for sub-50ms p99 latency in low-risk decisions:

- OPA evaluator embedded in-process (not a separate network hop)
- Policy decision cached for repeated identical actions (5-second TTL, configurable)
- Risk Engine uses pre-computed agent reputation from Trust Graph (Phase 4+); Phase 1 uses workflow-level static risk classification
- Audit emit and snapshot capture are async to the hot path; the action decision returns to the agent before the audit record is fully persisted (with strong durability guarantees on the async path)

---

## 10. Disaster recovery and replay

### 10.1 Recovery objectives

- **Audit Ledger:** RTO 30 seconds, RPO 0 (synchronous replication; no acceptable data loss)
- **Replay Vault:** RTO 5 minutes, RPO 1 minute (asynchronous replication)
- **Control Plane:** RTO 5 minutes, RPO 5 minutes
- **Reviewer Models:** RTO 10 minutes (model warm-up cost); RPO not applicable (stateless)

### 10.2 Backup and retention tiers

- **Hot tier** — Postgres primary + replicas, immediate query
- **Warm tier** — Postgres warm archive (older than 90 days), query within 60 seconds
- **Cold tier** — Object store immutable evidence vault (Glacier / Azure Archive / customer cold storage). Query within 24 hours.

Retention defaults are sector-aligned, not arbitrary:
- Internal pilot: 30–90 days hot, 1 year warm, no cold
- Enterprise production: 90 days hot, 1 year warm, 3 years cold
- Financial services / regulated: 90 days hot, 2 years warm, 7 years cold (FCA / PRA / EBA / SEC retention)
- Defence / public sector: 90 days hot, 2 years warm, configurable cold (legal-hold capable)

### 10.3 Replay mechanics

Replay reconstructs a past decision from the Replay Vault snapshot bundle:

1. User (auditor / regulator / operator) selects a decision by ID, workflow + timestamp, or query
2. Replay Service fetches the snapshot bundle: model version hash, prompt, tools, retrieved documents, RNG seed, reviewer verdicts, final decision
3. Verixa reconstructs the decision context — what the model saw, what policies applied, what the reviewers said, what the final routing was
4. Output: a structured replay record + optional re-execution of the reviewer triad against the historical package (to demonstrate consistency)

Replay is **snapshot-based**, not bit-exact regeneration of all external state. The historical record is what the system saw at the time; replay reconstructs what happened then, not what would happen now if the same inputs hit a current system.

A separate "what-if replay" feature lets the operator run a historical decision through the current policy + model + triad to compare past vs current behaviour. This is a distinct feature from primary replay and is clearly labelled.

---

## 11. AAGATE mapping appendix

Verixa's architecture maps to AAGATE's reference components:

| AAGATE component | Verixa equivalent | Notes |
|---|---|---|
| Governing-Orchestrator Agent (GOA) | Decision Router + Risk Engine + Trust Graph | Verixa's GOA equivalent is decomposed into three components |
| ComplianceAgent | Policy Engine (OPA + Rego) + Compliance Dossier Generator | Verixa explicitly uses OPA + Rego per AAGATE recommendation |
| Janus Shadow-Monitor Agent (SMA) | Triad Review Engine | Verixa extends Janus pattern from one mirror to three independent reviewers |
| Tool-Gateway Chokepoint | Runtime Gateway + Tool Call Firewall | Verixa decomposes into authentication + envelope (Gateway) and policy enforcement (Firewall) |
| Agent Name Service (ANS) | SPIFFE / SPIRE service identity | Verixa adopts SPIFFE per AAGATE recommendation |
| Service Mesh | Customer's existing service mesh (Phase 2–3) | Verixa does not ship Istio / Cilium; integrates with customer's mesh |
| Behavioural Analytics Pipeline | Trust Graph + Model Drift Monitor + Risk Engine | Verixa's behavioural analytics is graph-native rather than vector-DB-centric |
| ETHOS Ledger Hooks | Audit Ledger (optional cross-anchor) | Verixa Audit Ledger is hash-chained Postgres; optional cross-anchor to public ledger or customer-chosen evidence chain |

This mapping is the canonical AAGATE compatibility reference. It is included in the documentation pack delivered to enterprise customers and Big 4 advisors as the standards-body alignment artefact.

---

## 12. Open architecture decisions and Phase 2+ extensions

**Decisions deferred to Phase 2 design review:**

- Approval Matrix Engine — exact data model for authority chains (Phase 2 design starts with a pre-existing standard like NIST RBAC or XACML hierarchical role).
- Trust Graph schema — exact graph extension on Postgres (Apache AGE) vs external graph DB (Neo4j) for very large deployments. Decision driven by Phase 4 pilot data volumes.
- Cross-tenant federation in Federated Trust Mesh (Phase 6) — exact protocol for cross-organisation attestation. SPIFFE federation extension vs custom protocol vs adoption of an emerging trust-mesh standard.

**Phase 2+ architectural extensions:**

- Phase 2 adds: Approval Matrix Engine, Human Review Console, full Compliance Dossier Generator, Contradiction Detector, Hallucination Risk Engine, RBAC, sector compliance packs, input-side controls (PII redaction, prompt-injection detection)
- Phase 3 adds: Sovereign Runtime hardening, Model Drift Monitor, sidecar / service-mesh integration mode, private model registry, secure model execution
- Phase 4 adds: Trust Graph at full scope, WET Ops, reviewer quality tracking, workflow anomaly detection
- Phase 5 adds: Bench, Hallmark, Forge, Replica, third-party AI governance wrappers (Copilot, Salesforce, ServiceNow)
- Phase 6 adds: Federated Trust Mesh, cross-org attestation, supplier evidence sharing

Each phase has its own design review and SAD update before implementation begins.

---

*This System Architecture Document is the canonical technical reference for Verixa. The API Specification, Data Model, Threat Model, and Deployment Topology documents extend specific sections. The Build Plan operationalises the phased implementation sequence. SAD updates require Chief Architect approval and Phase Gate review.*
