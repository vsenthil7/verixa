# Verixa — Security Architecture

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: CISO, security architect, procurement security questionnaire reviewer, Big 4 advisor

---

## 1. Purpose

This document specifies Verixa's security architecture in detail. It complements the System Architecture Document (which covers the architectural surface) and the Threat Model (which covers the attack surface). This document covers the security controls and design decisions that implement Verixa's security posture.

The intended use of this document is:

- Customer security review during procurement (procurement officer + CISO)
- Big 4 advisor security assessment
- Internal Verixa security audit and certification preparation (SOC 2, ISO 27001, ISO 42001)
- Reference for engineering teams implementing or extending Verixa modules

---

## 2. Security principles

Verixa's security architecture is anchored on five principles:

1. **Sovereign by default for regulated tiers.** No customer data leaves the customer's trust boundary in Tier 1 (on-premises) or Tier 3 (sovereign managed). In Tier 4 (hosted SaaS) the trust boundary is the Verixa-operated tenant.
2. **Zero-trust within the platform.** No service is implicitly trusted. Every service-to-service interaction is authenticated and authorised. Every internal API is gated by OPA policies (Verixa dogfoods its own product).
3. **Cryptographic non-repudiation by default.** The audit ledger is hash-chained and Ed25519-signed. Triad reviews use commit-and-reveal cryptographic protocol. Replay Vault snapshots are content-addressable and AES-256-GCM encrypted.
4. **Least privilege at every layer.** Agent roles, human roles, service identities, key access, network access — all default-deny, opt-in by explicit policy.
5. **Auditable security operations.** Every administrative action against Verixa is itself an audit ledger entry. Verixa's own admin operations are audited the same way customer agent actions are audited.

---

## 3. Identity architecture

### 3.1 Service identity (SPIFFE/SPIRE)

Every Verixa internal service has a SPIFFE ID. SPIRE issues short-lived (1-hour) workload certificates to each service. mTLS between services uses SPIRE-issued certificates.

SPIFFE ID structure:
```
spiffe://verixa.{tenant_id}.{deployment_topology}/services/{service_name}
```

Example:
```
spiffe://verixa.customer-bank-example.sovereign-managed/services/runtime-gateway
spiffe://verixa.customer-bank-example.sovereign-managed/services/triad-reviewer-a
```

SPIRE deployment options per topology:
- **Tier 1 (on-prem):** Verixa SPIRE server in customer environment; customer-controlled root CA option
- **Tier 2 (private cloud):** Verixa SPIRE server in customer's cluster
- **Tier 3 (sovereign managed):** Verixa-operated SPIRE server in dedicated tenant
- **Tier 4 (hosted SaaS):** Verixa-operated multi-tenant SPIRE with per-tenant trust domain isolation

Phase 6 introduces SPIFFE federation for cross-tenant attestation in the Federated Trust Mesh.

### 3.2 Agent identity (customer's AI agents)

Customer's AI agents authenticate to Verixa Runtime Gateway via:
- **Phase 1:** API keys (rotated quarterly) or mTLS client certificates issued by customer's PKI
- **Phase 2+:** SPIFFE workload identity (customer's SPIRE federated with Verixa's SPIRE)
- **Phase 3+:** OAuth 2.0 client credentials grant for higher-friction integrations

Agent identity is bound to the agent registry record. Every governed action carries the agent's SPIFFE ID (or equivalent identifier) and is recorded in the audit ledger.

### 3.3 Human identity

Human users authenticate to Verixa Control Plane via:
- **OIDC** (preferred) — federated to customer's IdP (Okta, Azure AD / Entra ID, Google Workspace, Ping, ADFS)
- **SAML 2.0** — for customers with SAML-only IdP infrastructure
- **MFA required** for production environment access; enforced at the customer's IdP

RBAC roles (Phase 2+):
- `admin` — platform administration; can manage tenants, deployments, signing keys
- `policy_author` — can author and version Rego policies
- `reviewer` — can act on Human Review Console queues
- `auditor` — read-only access to audit ledger, replay vault, dossiers
- `viewer` — read-only access to dashboards and metrics
- `developer` — read-only access to operational APIs and metrics; no audit-data access

Roles are mapped from customer IdP groups via OIDC/SAML group claims. Custom role bindings are managed through the Approval Matrix Engine.

---

## 4. Cryptographic architecture

### 4.1 Algorithm choices

| Use | Algorithm | Notes |
|---|---|---|
| Hash chain for audit ledger | SHA-256 | Industry standard; FIPS 140-3 acceptable; future migration to SHA-3 if needed |
| Audit ledger entry signing | Ed25519 | Compact, fast, FIPS 186-5 acceptable |
| Triad commit-reveal | SHA-256(verdict ∥ nonce) | Standard cryptographic commitment scheme |
| Replay Vault encryption | AES-256-GCM | Authenticated encryption with associated data |
| TLS for all external endpoints | TLS 1.3 | Older versions explicitly disabled |
| mTLS internal | TLS 1.3 with client certificates | SPIFFE-issued certificates |
| Webhook signing | Ed25519 | Same algorithm as audit ledger |
| Customer IAM bridge | OIDC with JWS (RS256 / ES256) | Customer-IdP-determined |

### 4.2 Key hierarchy

```text
                          [Tenant Master Key]
                           (in customer Vault for Tier 1/2/3;
                            in Verixa Vault for Tier 4)
                                  |
                ┌─────────────────┼─────────────────┐
                v                 v                 v
       [Audit Signing Key]  [Replay Vault    [Webhook Signing
       (Ed25519,             Encryption Key]  Key]
        rotated quarterly)   (AES-256,        (Ed25519,
                              per-workflow     rotated annually)
                              sub-keys via
                              KDF)
```

Key rotation:
- **Audit signing keys** rotated quarterly. Old keys retained indefinitely for verification of historical entries. Key rotation events are themselves audit ledger entries.
- **Replay Vault encryption keys** rotated annually. Snapshot bundles are re-keyed on access if old key is rotated; original encrypted bundles preserved for integrity proof purposes.
- **Webhook signing keys** rotated annually.
- **Triad commit nonces** are per-decision, ephemeral.

### 4.3 Key storage

- **Tier 1 (on-prem):** customer-deployed HashiCorp Vault; Verixa never sees private key material
- **Tier 2 (private cloud):** customer-deployed Vault or cloud KMS (AWS KMS, Azure Key Vault, GCP KMS) with Verixa as authorised consumer
- **Tier 3 (sovereign managed):** Verixa-operated Vault per dedicated tenant; HSM-backed in regulated-sector deployments
- **Tier 4 (hosted SaaS):** Verixa-operated multi-tenant Vault with per-tenant key hierarchy

Key access is authenticated, authorised, and audited at the Vault layer. Verixa staff cannot extract private keys from Vault even with admin access; key operations (sign, encrypt) are performed inside Vault.

### 4.4 Quantum-readiness

Verixa monitors NIST PQC (post-quantum cryptography) standardisation. Migration plan:
- **Hash chain** stays on SHA-256 until SHA-3 is broadly adopted; SHA-256 not threatened by current quantum advances
- **Signatures** plan migration to a NIST-approved post-quantum signature (e.g. ML-DSA / Dilithium) when standardised and widely supported. Hybrid signing (Ed25519 + post-quantum) feasible via dual-signature audit ledger entries
- **Encryption** stays on AES-256 (Grover's algorithm reduces effective security to 128 bits, still sufficient); supplemental hybrid KEM if customer requires

---

## 5. Network architecture

### 5.1 Network segmentation

```text
+---------------------------------------------------------------+
|                        Customer Trust Boundary                  |
|                                                                |
|   +------------------+   +------------------+                  |
|   | Hot-path runtime |   | Reviewer models  |                  |
|   | network          |   | network          |                  |
|   | (Runtime Gateway,|<->| (vLLM-on-ROCm,   |                  |
|   |  Tool Firewall,  |   |  MI300X)         |                  |
|   |  Policy, Risk)   |   | NO INTERNET      |                  |
|   +------------------+   | EGRESS           |                  |
|                          +------------------+                  |
|                                                                |
|   +------------------+   +------------------+                  |
|   | Control plane    |   | Storage network  |                  |
|   | network          |<->| (Postgres, Object|                  |
|   | (Admin API, UI)  |   |  Store, Vault)   |                  |
|   +------------------+   +------------------+                  |
|                                                                |
|   +------------------+   +------------------+                  |
|   | Webhook egress   |-->| Customer SIEM /  |                  |
|   | (signed events)  |   | ITSM endpoints   |                  |
|   +------------------+   +------------------+                  |
|                                                                |
+---------------------------------------------------------------+
```

Network segmentation rules:
- Hot-path runtime, control plane, reviewer models, and storage are on separate networks
- Reviewer model network has **no outbound internet egress** in Tier 1/2/3 deployments — sovereign verifier guarantee
- Storage network is reachable only from runtime, control plane, and approved background jobs
- Control plane is the only network exposed to authenticated humans
- Webhook egress is allow-listed to customer-specified destinations only

### 5.2 Ingress and egress controls

- **Ingress:** TLS 1.3 termination at customer's load balancer (Tier 1) or Verixa-operated load balancer (Tier 3/4); Web Application Firewall in front of public endpoints (Tier 4); per-tenant IP allow-list options
- **Egress:** allow-list per network; reviewer model network allow-list is empty; control plane allow-list includes Verixa update repository (signed packages) and customer-configured webhook destinations only
- **DNS:** customer-controlled DNS resolver in Tier 1; Verixa-controlled in Tier 3/4

### 5.3 Inter-tenant isolation

- **Tier 1 / 2 / 3:** physical or logical infrastructure isolation; no shared compute, storage, or network plane between tenants
- **Tier 4 (hosted SaaS):** logical isolation via per-tenant Postgres databases, per-tenant object-store prefixes, per-tenant Vault namespaces, per-tenant SPIFFE trust domains; row-level security as defence-in-depth

---

## 6. Container and supply chain security

### 6.1 Container hardening

Verixa container images:
- Base on minimal distroless or hardened Alpine images
- CIS-benchmark-aligned hardening (no unused services, no debug shells in production, read-only root filesystem, non-root user)
- No SSH, no root shell, no SUID binaries
- Image size minimised (typically < 200 MB per service)

### 6.2 Image signing and verification

- Every Verixa container image is signed with Cosign (Sigstore)
- SBOM (Software Bill of Materials) generated per release and published alongside the image
- Image deployment pipeline verifies signature before scheduling; deployments fail closed on signature mismatch

### 6.3 Dependency management

- Dependency pinning at the lockfile level (poetry.lock for Python; package-lock.json for Node)
- Renovate / Dependabot for dependency update PRs
- Snyk / Trivy for vulnerability scanning at build time and on running images
- CVE patching SLA: 7 days critical, 30 days high, 90 days medium

### 6.4 Build pipeline integrity

- Builds run in ephemeral CI runners with no inbound access
- Build artefacts published to Verixa's signed package repository
- Build provenance attestation (SLSA Level 3+ target)
- Phase 5 Hallmark module extends provenance attestation to customer's primary AI models

---

## 7. Application security

### 7.1 Input validation

- Every API endpoint validated via Pydantic v2 (Python) or Zod (TypeScript)
- Schema validation at the gateway layer; malformed requests rejected before reaching business logic
- JSON depth and size limits enforced
- Tool argument bounds enforced at Tool Call Firewall

### 7.2 Output encoding

- API responses are JSON; no HTML rendering on backend APIs
- Control Plane UI is React with default-safe rendering; no innerHTML usage
- Webhook payloads are JSON with explicit schema versioning

### 7.3 Injection defences

- Postgres queries use parameterised statements only (SQLAlchemy 2.0 async ORM)
- Rego policy evaluation is sandboxed (OPA's evaluation model)
- Tool calls to customer systems are validated against registered schemas before forwarding

### 7.4 Authentication and session management

- OIDC ID tokens validated against customer IdP's JWKS endpoint; nonce + audience + expiry checks enforced
- Session tokens are short-lived (15 minutes default) with refresh via OIDC refresh tokens
- API keys stored as bcrypt-hashed values; never logged in plaintext

### 7.5 OWASP Top 10 web alignment

Verixa Control Plane is reviewed against OWASP Top 10 Web 2021:
- A01 Broken Access Control — RBAC + OPA-gated internal APIs
- A02 Cryptographic Failures — TLS 1.3 + Ed25519 + AES-256-GCM (see §4)
- A03 Injection — parameterised queries, schema validation, Rego sandboxing
- A04 Insecure Design — threat modelling at every phase
- A05 Security Misconfiguration — CIS-benchmark-aligned hardening
- A06 Vulnerable and Outdated Components — dependency scanning, SBOM, patch SLA
- A07 Identification and Authentication Failures — OIDC + MFA at IdP + short sessions
- A08 Software and Data Integrity Failures — signed images + Cosign verification
- A09 Security Logging and Monitoring Failures — internal admin operations are audit ledger entries
- A10 Server-Side Request Forgery — egress allow-lists, no internet egress for reviewer models

---

## 8. Operational security

### 8.1 Incident response

Published incident response runbook with:
- Severity classification (S1–S4)
- Escalation matrix per severity
- Customer notification SLA per severity (S1 = within 4 hours; S2 = 12 hours; S3 = 48 hours; S4 = next business day)
- Forensic capture procedures
- Post-incident review template
- 24/7 incident response team for Tier 3 / 4

### 8.2 Vulnerability disclosure

- Public security@ inbox for responsible disclosure
- Bug bounty programme (Phase 2+)
- 90-day coordinated disclosure window
- Public security advisories for material vulnerabilities

### 8.3 Penetration testing

- Annual third-party penetration test on Tier 3 / 4 deployments
- Customer-led penetration testing welcomed and supported in Tier 1 / 2
- Red-team exercises annual for the platform; quarterly for the reviewer triad layer specifically

### 8.4 Security operations centre

- 24/7 SecOps for Tier 3 / 4
- SIEM integration: Verixa's own audit ledger flows to internal Verixa SIEM; customer's audit data optionally flows to customer SIEM
- Anomaly detection on internal admin operations

### 8.5 Staff security

- Staff vetting per regulated-sector requirements (DBS check UK, equivalents EU)
- Need-to-know access; role-based access control on customer data
- Staff cannot decrypt Replay Vault bundles in Tier 1 / 2 / 3 (customer-managed key hierarchy)
- Quarterly security awareness training; specific AI-attack-pattern training

---

## 9. Compliance and certification roadmap

| Certification / attestation | Phase target | Notes |
|---|---|---|
| SOC 2 Type I | Phase 2 (Q1 2027) | Initial readiness |
| SOC 2 Type II | Phase 3 (Q3 2027) | Continuous attestation |
| ISO 27001 | Phase 3 (Q3 2027) | Information Security Management |
| ISO/IEC 42001 | Phase 3 (Q3 2027) | AI Management System — Verixa is a likely first-cohort certified vendor |
| ISO 27017 | Phase 4 (Q4 2027) | Cloud security extension |
| ISO 27018 | Phase 4 (Q4 2027) | PII in cloud |
| Cloud Security Alliance STAR Level 2 | Phase 3 (Q3 2027) | CSA STAR with CCM + AICM mapping |
| FedRAMP Moderate | Phase 5 (Q2 2028) | US public sector |
| Cyber Essentials Plus | Phase 2 (Q1 2027) | UK government baseline |

---

## 10. Customer security artefacts

For customer security review, Verixa provides on request:

- Most recent SOC 2 / ISO certificates (when available)
- Penetration test executive summary (annually)
- Recent vulnerability scan summary
- Information Security questionnaire response (CAIQ-based, sector-extended)
- Data Processing Agreement (DPA)
- Master Services Agreement (MSA) with security schedule
- Sovereign deployment topology agreement (Tier 1 / 3)
- Threat Model document (linked from this documentation pack)
- Architecture review session with Verixa security architect

---

*This Security Architecture document is the canonical security reference for Verixa. The Threat Model assesses the attack surface; this document specifies the control surface. The System Architecture Document defines the components being secured. The Regulatory Mapping Matrix maps controls to regulatory obligations. Updates require Security Architect approval and quarterly review.*
