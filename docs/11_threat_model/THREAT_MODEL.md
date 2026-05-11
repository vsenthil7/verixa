# Verixa — Threat Model

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: CISO, security architect, Big 4 advisor, regulator-facing audit team

---

## 1. Methodology

This Threat Model uses three analytical frames in combination:

- **STRIDE** — the classic Microsoft Security Development Lifecycle taxonomy: Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege.
- **OWASP Top 10 for Large Language Model Applications (2025 edition)** — LLM-specific risks: prompt injection, insecure output handling, training data poisoning, model denial of service, supply chain vulnerabilities, sensitive information disclosure, insecure plugin design, excessive agency, overreliance, model theft.
- **AAGATE-named risk classes** — LPCI (Logic-layer Prompt Control Injection), QSAF (Cognitive Degradation), DIRF (Digital Identity Rights misuse), Supply-Chain Blindness.

Each identified threat is rated on:
- **Likelihood** — Low / Medium / High based on attacker motivation, capability requirement, attack surface exposure
- **Impact** — Low / Medium / High based on operational, regulatory, and reputational consequence
- **Risk** — derived from Likelihood × Impact, expressed Low / Medium / High / Critical
- **Mitigation status** — Mitigated / Mitigated by Phase 2+ / Mitigated by external control / Residual risk accepted

---

## 2. System threat surface (high-level)

```
                                              [Adversary]
                                                  |
   +------------------- attack surfaces -----------+----------------+
   |                |                  |           |                |
   v                v                  v           v                v
[Customer's     [Verixa Runtime    [Verixa     [Verixa         [Verixa
 AI Agents]      API surface]      Control     Storage]        Reviewer
   ↑                                Plane]                      Models]
   | governs
   |
[Customer's    
 systems]                                    [Customer's       [Webhook
                                              IAM, SIEM,        endpoints
                                              Vault]            in customer
                                                                systems]
```

Verixa sits in the customer's trust boundary in Tier 1 (on-prem) and Tier 3 (sovereign managed). The threat model below addresses both Verixa-internal threats and Verixa-to-customer-system integration threats.

---

## 3. STRIDE analysis

### 3.1 Spoofing

| ID | Threat | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| S-1 | Attacker spoofs a customer agent identity to bypass agent-specific policies | Medium | High | High | mTLS + SPIFFE IDs at Runtime Gateway; agent identity bound to short-lived workload certificates not API keys (Phase 2); tenant-bound agent registry |
| S-2 | Attacker spoofs a Verixa internal service (e.g. impersonates Reviewer Model to inject favourable verdicts) | Low | Critical | High | SPIFFE/SPIRE service identity for all Verixa containers; mTLS between containers; Triad commit-and-reveal protocol means an injected verdict would have to also forge the hash commit (cryptographically infeasible) |
| S-3 | Attacker spoofs the Verixa Control Plane to a customer reviewer (phishing) | Medium | High | High | OIDC/SAML via customer IAM; customer-controlled identity, MFA required; published Verixa Control Plane URL pinned in customer documentation |
| S-4 | Attacker spoofs a regulator request to extract dossiers | Low | High | Medium | Dossier export requires authenticated control plane operation by RBAC-authorised personnel; dossier transmission outside Verixa is the customer's responsibility |
| S-5 | Customer staff spoofs a higher-authority approver via Approval Matrix | Low | High | Medium | RBAC + customer IAM; Approval Matrix Engine enforces role bindings; approval actions require MFA at customer IAM level |

### 3.2 Tampering

| ID | Threat | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| T-1 | Attacker tampers with audit ledger entries to remove evidence of policy violation | Low | Critical | High | Hash-chained audit ledger with Ed25519 signatures; integrity verification walks the chain from any entry to genesis; tampered entry breaks the chain and is detectable |
| T-2 | Attacker tampers with hash-chain itself (e.g. truncate then re-sign) | Very Low | Critical | High | Signing keys are in HashiCorp Vault, never on application servers; Vault access requires authenticated operators; signing key rotation quarterly; old keys retained for verification of historical entries; optional cross-anchor to public ledger or customer-chosen evidence chain for tamper-evident anchoring |
| T-3 | Attacker tampers with Replay Vault snapshot bundles | Low | Critical | High | Bundles are content-addressable (object key includes content hash); bundle manifest hash is committed to audit ledger; bundle encryption AES-256-GCM with per-tenant key hierarchy; integrity check on every replay request |
| T-4 | Attacker tampers with Rego policies in flight (man-in-the-middle to inject permissive policies) | Low | High | Medium | Policies are signed at Compile time; Policy Engine verifies signature on policy load; in-flight policy modification requires Control Plane API admin authentication |
| T-5 | Attacker tampers with model weights on Reviewer Model deployment | Low | High | Medium | Models loaded from signed artefacts; model version hash recorded in registry; Verixa records reviewer model identity hash in every triad review record; reviewer model integrity is verified at startup |
| T-6 | Attacker tampers with Trust Graph relationships to hide drift or incident lineage | Low | High | Medium | Trust Graph updates are sourced from audit ledger only (single source of truth); direct database write to Trust Graph requires DBA-level credentials behind Vault |
| T-7 | LPCI (Logic-layer Prompt Control Injection) — prompt injection in retrieved documents tampers with primary agent reasoning before Verixa intercepts the action | High | Medium | High | Phase 2 input-side controls (PII redaction, prompt-injection detection, context risk scoring); Triad Review on high-risk decisions catches downstream effects of input-layer attacks; Evidence Validator surfaces ungrounded claims |

### 3.3 Repudiation

| ID | Threat | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| R-1 | Customer's reviewer denies making an approval decision after the fact | Low | High | Medium | Human Review records include reviewer identity + IAM authentication trace + decision timestamp + signed audit ledger entry; non-repudiation by cryptographic signature |
| R-2 | Verixa internally denies that a triad review occurred | Very Low | High | Low | Triad commit-and-reveal records are stored with signed hashes from each reviewer; impossible to retroactively claim the review didn't happen without breaking the audit ledger chain |
| R-3 | Customer's agent denies submitting an action that Verixa records | Low | Medium | Low | Action requests carry SPIFFE identity + workload signature + trace ID; trace ID correlates to customer-side OpenTelemetry trace if customer enables; non-repudiation by SPIFFE identity |
| R-4 | Regulator disputes the integrity of an Annex IV-aligned dossier | Low | Critical | Medium | Dossier includes hash-chain proof and signed bundle metadata; regulator can verify dossier authenticity by replaying hash chain from genesis |

### 3.4 Information disclosure

| ID | Threat | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| I-1 | Replay Vault snapshot bundles leak sensitive customer prompts/PII | Low | Critical | High | Per-tenant AES-256-GCM encryption; per-customer-or-per-workflow key hierarchy in Vault; bundles inaccessible without authenticated Replay Service operation by RBAC-authorised personnel |
| I-2 | Audit ledger leaks workflow context across tenants | Very Low | Critical | Medium | Postgres row-level security on tenant_id; single-tenant Postgres instance in Tier 1/2/3 deployments; tenant-bound application connection pools |
| I-3 | Triad Review payloads contain sensitive prompts; reviewer models leak prompts to external destinations | Very Low | High | Low | Reviewer models run sovereign on customer's MI300X (Sovereign Verifier mode); models do not have outbound internet access in Verixa-managed deployments; Phase 1 deploys reviewer models with no network egress except to Verixa Runtime Container |
| I-4 | Trust Graph queries leak supplier or reviewer information cross-tenant | Very Low | High | Low | Trust Graph is per-tenant; cross-tenant graph queries are only enabled for Federated Trust Mesh (Phase 6) and require explicit cross-org attestation handshake |
| I-5 | Webhook payloads to customer SIEM leak across customer environments due to misrouted URLs | Low | High | Medium | Per-tenant webhook destination configuration; signed webhooks with customer-side signature verification; misrouted webhook delivery failures alerted to Verixa SRE |
| I-6 | Sensitive Information Disclosure (OWASP LLM06) — primary agent's response leaks PII or confidential data into Verixa context | Medium | Medium | Medium | Phase 2 PII redaction at input; Replay Vault bundles encrypted; access to bundles requires authenticated request; data subject requests handled per DPA |
| I-7 | Verixa staff with admin access leak customer data | Low | Critical | High | Customer-managed key hierarchy in Tier 1/2/3 means Verixa staff cannot decrypt Replay Vault bundles without customer-side Vault access; Verixa internal RBAC + audit on internal admin operations; staff vetting per regulated-sector requirements |

### 3.5 Denial of service

| ID | Threat | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| D-1 | Customer agent DoSes Runtime Gateway with high-volume action requests | Medium | High | High | Per-tenant + per-API-key + per-endpoint rate limits; gateway-level throttling; tenant resource quotas in Sovereign Managed and Hosted SaaS tiers |
| D-2 | Triad Review GPU-saturation by malicious or buggy customer agent flooding high-risk actions | Low | High | Medium | Triad invocation is gated by Risk Engine threshold; sustained high-risk volume triggers operational alert; reviewer model GPU is dedicated per Sovereign tenant; capacity scaling via additional MI300X allocation |
| D-3 | Audit ledger Postgres saturation under high write throughput | Low | High | Medium | Postgres tuning, primary-replica setup, write-back queue with bounded buffer, async audit emit on hot path; runtime decision returns to agent before audit fully persisted (with strong durability on async path) |
| D-4 | Replay Vault object store exhaustion (storage cost attack) | Low | Medium | Low | Per-tenant storage quotas; retention tier movement (warm + cold) reduces hot-tier cost; alerting on quota approach |
| D-5 | Customer's IAM (OIDC/SAML) outage cascades to Verixa Control Plane unavailability | Medium | Medium | Medium | Cached IAM tokens with short TTL; degraded-mode fallback to last-known-good RBAC for in-progress sessions; documented IAM-outage runbook |
| D-6 | Model Denial of Service (OWASP LLM04) — adversarial inputs cause reviewer models to consume excessive compute | Low | Medium | Low | Reviewer model invocation has hard timeout (default 30 seconds, configurable); timeout produces structured "no_verdict" reviewer outcome which is treated per disagreement policy; tenant alerted on persistent timeouts |

### 3.6 Elevation of privilege

| ID | Threat | Likelihood | Impact | Risk | Mitigation |
|---|---|---|---|---|---|
| E-1 | Customer staff escalates from reviewer role to admin role within Verixa Control Plane | Low | Critical | High | RBAC enforced at Control Plane API; role assignment is customer-IAM-controlled; OPA policies on internal admin operations gate role-elevation paths |
| E-2 | Verixa staff escalates from operations role to access customer data | Low | Critical | High | Customer-managed key hierarchy in Tier 1/2/3; Verixa-side RBAC on internal operations; staff vetting and operational SOPs per regulated-sector requirements |
| E-3 | Compromised reviewer model produces verdicts that escalate the privileges of an attacker's agent | Very Low | High | Medium | Triad consensus required for high-risk; single compromised reviewer cannot override the other two without breaking commit-and-reveal protocol; model integrity verified at startup |
| E-4 | Excessive Agency (OWASP LLM08) — primary agent given over-broad Verixa-governed permissions, attacker exploits the agent to perform actions outside intent | High | High | High | Tool Call Firewall enforces allow-list per agent role; argument bounds per role; Approval Matrix Engine on high-risk actions; least-privilege agent roles enforced at registration |
| E-5 | Compromised customer-side Vault grants attacker access to Verixa signing keys | Very Low | Critical | Medium | Vault access requires multiple authentication factors per Vault policy; signing key access is audited; keys rotated quarterly; old keys retained for verification only |

---

## 4. AAGATE-named risk class analysis

### 4.1 LPCI — Logic-layer Prompt Control Injection

**Threat:** Hidden payloads in retrieved documents, tools, or memory that bypass input validation and influence the agent's reasoning chain. Closer in spirit to SQL injection than to popular-meaning "prompt injection" in chat interfaces.

**Verixa exposure:**
- Primary agent's retrieved documents are upstream of Verixa interception
- LPCI may have already shifted the agent's intent by the time Verixa sees the action
- Phase 1 mitigation: Verixa governs the *action* not the *prompt*; even if LPCI shifts agent reasoning, Verixa's Tool Call Firewall + Policy Engine + Risk Engine + Triad Review still gate the resulting action
- Phase 2 mitigation: input-side controls (prompt-injection detection, context risk scoring, source-document trust scoring) directly address LPCI at the input boundary

**Residual risk:** Medium. Verixa is action-side governance; perfect input-side protection is not guaranteed by any tool. Verixa's value is that even if LPCI succeeds at the input layer, the action layer is still governed.

### 4.2 QSAF — Cognitive Degradation

**Threat:** Reasoning instability from recursive or overloaded agent sessions; the agent's quality degrades over a session through compound prompt manipulation or excessive context.

**Verixa exposure:**
- Per-action Verixa governance is stateless from the agent's perspective; QSAF affects the agent's reasoning, not Verixa's enforcement
- Phase 4 Trust Graph captures agent drift over time, surfacing degradation patterns
- Phase 4 Model Drift Monitor detects QSAF symptoms across many sessions

**Residual risk:** Medium. Verixa surfaces the symptoms; remediation requires customer-side agent design changes.

### 4.3 DIRF — Digital Identity Rights misuse

**Threat:** Unauthorised replication or monetisation of a digital likeness; deepfake or impersonation attacks on enterprise AI agents.

**Verixa exposure:**
- Verixa governs agent actions; identity-rights misuse is a content-layer concern outside Verixa's direct scope
- Phase 5 Hallmark module addresses provenance and attestation for content; cryptographic provenance for outputs that leave the customer's environment
- Phase 1 mitigation: agents are SPIFFE-identified, so impersonation of a Verixa-registered agent is technically distinct from broader DIRF risks

**Residual risk:** Higher in Phase 1 (Hallmark not yet built); reduces materially in Phase 5.

### 4.4 Supply-Chain Blindness

**Threat:** Unverified models, unsigned images, untracked dependencies propagating across environments without provenance evidence.

**Verixa exposure:**
- Verixa's own supply chain: signed OCI images, SBOMs published with each release, Cosign verification on container deployment, signed Rego policy artefacts
- Customer's primary AI agent supply chain: Verixa registers model versions and hashes in `verixa_registry.models`; cross-references model identity in every audit entry; Phase 5 Hallmark provides full provenance attestation
- Phase 4 Trust Graph supplier nodes track third-party AI/SaaS suppliers and their incident lineage

**Residual risk:** Low for Verixa's own supply chain; medium for customer's primary supply chain in Phase 1, decreasing in Phase 5 with Hallmark.

---

## 5. OWASP Top 10 for LLMs cross-reference

| OWASP LLM Risk | Verixa coverage |
|---|---|
| LLM01: Prompt Injection | Phase 2 input controls + action-side governance always-on (Phase 1+) |
| LLM02: Insecure Output Handling | Tool Call Firewall + argument bounds + Evidence Validator |
| LLM03: Training Data Poisoning | Out of scope at Phase 1 (Verixa does not train models); Phase 5 Hallmark provenance attestation |
| LLM04: Model Denial of Service | Rate limits + reviewer model timeouts + Risk Engine throttling |
| LLM05: Supply Chain Vulnerabilities | Signed OCI + SBOM + Cosign for Verixa; Phase 5 Hallmark for customer model supply chain |
| LLM06: Sensitive Information Disclosure | Phase 2 PII redaction + Replay Vault encryption + RBAC on dossier access |
| LLM07: Insecure Plugin Design | Tool Call Firewall enforces tool schema + argument bounds + per-role allow-list |
| LLM08: Excessive Agency | Tool Call Firewall + Approval Matrix Engine + least-privilege role registration |
| LLM09: Overreliance | Triad Review surfaces disagreement; Evidence Validator surfaces ungrounded claims; Trust Graph surfaces drift |
| LLM10: Model Theft | Reviewer models run sovereign with no outbound network egress; primary model theft is customer's responsibility |

---

## 6. Trust boundaries and assumptions

**Trusted:**
- Customer's IAM and Vault are trusted within their stated security posture (customer responsibility)
- Customer's MI300X firmware and ROCm runtime are trusted per AMD's stated security posture
- Postgres, Redis, OPA, vLLM, FastAPI are trusted within their respective security postures
- Cryptographic primitives (SHA-256, Ed25519, AES-256-GCM) are trusted per current state of cryptography

**Not trusted:**
- Customer's AI agents are not trusted; they are governed
- Customer's tools and downstream systems are not trusted; Tool Call Firewall enforces
- Retrieved documents are not trusted; Evidence Validator + Phase 2 prompt-injection detection
- Third-party AI products integrated in Phase 5 are not trusted; governed via API wrappers

**Out of scope for Verixa Threat Model:**
- Physical security of customer's data centres
- Hardware-level attacks on MI300X (side channels, fault injection) — addressed by AMD's hardware security posture
- Compromise of customer's IAM — addressed by customer's security architecture
- Insider threats at the customer's own organisation — addressed by customer's security architecture

---

## 7. Operational security controls (summary)

- **Penetration testing** — annual independent penetration test on Verixa-managed deployments (Tier 3, Tier 4); customer-led penetration testing supported and welcomed in Tier 1, Tier 2
- **Vulnerability management** — CVE monitoring, automated dependency scanning, patch SLA: 7 days for critical, 30 days for high, 90 days for medium
- **Security incident response** — published runbook, 24/7 incident response team for Tier 3, Tier 4; documented escalation to customer security teams
- **SOC 2 Type II audit** — Phase 2 deliverable; updated annually
- **ISO 27001 certification** — Phase 3 deliverable
- **ISO 42001 certification** (AI Management Systems) — Phase 3 deliverable; Verixa dogfoods its own product to maintain ISO 42001 conformance
- **Secure software development lifecycle** — threat modelling for every major feature; security review before phase gates; CIS-benchmark-aligned container hardening

---

## 8. Threat model maintenance

This Threat Model is updated:
- At every phase gate (1→2, 2→3, 3→4, 4→5, 5→6) — phase-gate review includes threat-model delta
- On any new attack class identified in customer environments
- On any CVE in critical dependencies
- Quarterly review by Verixa Security Architect + at least one external reviewer

---

*This Threat Model document is the canonical security analysis reference for Verixa. The System Architecture Document defines the components being threat-modelled. The Data Model defines the persistence layer attack surface. The Regulatory Mapping Matrix shows how threat mitigations map to specific regulatory controls.*
