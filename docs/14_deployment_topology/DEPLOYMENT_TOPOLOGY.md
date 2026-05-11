# Verixa — Deployment Topology

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: CIO, infrastructure architect, deployment engineer, procurement officer

---

## 1. Topology overview

Verixa supports four deployment topologies. All four are first-class commercial options; none is a premium add-on. The same Verixa codebase deploys to all four; differences are in operational responsibility, key management hierarchy, tenancy model, and SLA.

| Topology | Compute location | Verixa operational role | Customer operational role | Pricing tier |
|---|---|---|---|---|
| **On-premises** | Customer-owned MI300X | Application support | Infrastructure, network, IAM, Vault, MI300X | Tier 2 Enterprise |
| **Private cloud** | Customer's private cloud + MI300X capacity | Application support | Cloud account, network, IAM, Vault, MI300X provisioning | Tier 2 Enterprise |
| **Sovereign managed** | Verixa-operated dedicated tenancy on AMD Developer Cloud | Full-stack operation in dedicated tenant | IAM federation, customer-side integrations | Tier 3 Sovereign Managed |
| **Hosted SaaS** | Verixa-operated multi-tenant on AMD Developer Cloud | Full-stack operation, multi-tenant | Customer integration consumer | Tier 4 Hosted SaaS |

This document specifies each topology's architecture, operational responsibilities, security boundaries, and integration requirements.

---

## 2. On-premises topology (Tier 2 Enterprise — customer-owned MI300X)

```text
+----------------------------------------------------------------+
|                  Customer Data Centre                            |
|                                                                  |
|   +---------------------------------------+                      |
|   | Customer's existing infrastructure     |                      |
|   | - Network (DC fabric, firewalls)       |                      |
|   | - IAM (Active Directory / Okta)        |                      |
|   | - HashiCorp Vault                      |                      |
|   | - SIEM / ITSM / Audit                  |                      |
|   +---------------------------------------+                      |
|                                                                  |
|   +---------------------------------------+                      |
|   | Customer MI300X cluster                |                      |
|   | - 4–32 MI300X accelerators (sized to   |                      |
|   |   customer workload)                    |                      |
|   | - ROCm 7.x runtime                      |                      |
|   +---------------------------------------+                      |
|                  ^                                                |
|                  |                                                |
|   +---------------------------------------+                      |
|   | Verixa deployment                      |                      |
|   |                                        |                      |
|   | Kubernetes cluster (customer-managed)  |                      |
|   |  + Verixa Helm charts                  |                      |
|   |  + Postgres 16 (customer-managed HA)   |                      |
|   |  + Object store (customer-managed)     |                      |
|   |  + Redis (customer-managed)            |                      |
|   |  + SPIRE server (Verixa-deployed,      |                      |
|   |    customer-rooted)                    |                      |
|   |  + Reviewer model deployments on       |                      |
|   |    customer MI300X via vLLM-on-ROCm    |                      |
|   +---------------------------------------+                      |
|                                                                  |
+------------------------------------------------------------------+
```

**Customer responsibilities:**
- MI300X cluster procurement, deployment, patching
- Kubernetes cluster lifecycle (Verixa supports any CNCF-conformant cluster: vanilla Kubernetes, OpenShift, Rancher, etc.)
- Postgres HA setup, backup, monitoring
- Object store (MinIO with erasure coding, or customer's existing S3-compatible store)
- Network architecture, firewalls, segmentation
- IAM (Active Directory / Okta / Azure AD / Entra ID) with OIDC or SAML federation
- HashiCorp Vault deployment and operation
- SIEM and ITSM integration endpoints
- Sovereign-data sign-off for any data exiting the customer trust boundary

**Verixa responsibilities:**
- Verixa application installation (Helm charts)
- Application updates (signed packages)
- Application support per SLA
- Security patches for Verixa containers
- Triad reviewer model deployment configuration on customer MI300X
- Compliance Dossier rendering
- Customer Success engineer engagement during pilot and ongoing

**Use case fit:**
- Tier 1 banks with on-premises infrastructure mandates
- Defence and public sector with sovereign-data requirements
- Healthcare with data-residency obligations
- Energy / CNI with operational technology isolation requirements

**Operational SLA:**
- Verixa software support: 99.5% application availability (24/7 for Tier 2 with premium support add-on)
- Customer is responsible for infrastructure availability
- Joint incident response runbook

---

## 3. Private cloud topology (Tier 2 Enterprise — customer's private cloud)

```text
+----------------------------------------------------------------+
|                Customer's Private Cloud                          |
|                (sovereign region / dedicated tenancy)            |
|                                                                  |
|   +---------------------------------------+                      |
|   | Cloud-native infrastructure            |                      |
|   | - Cloud IAM (federated to customer's   |                      |
|   |   corporate IAM)                       |                      |
|   | - Cloud KMS (AWS KMS / Azure Key Vault |                      |
|   |   / GCP KMS) or customer Vault         |                      |
|   | - Cloud SIEM integration (Sentinel /   |                      |
|   |   GuardDuty / Chronicle)               |                      |
|   +---------------------------------------+                      |
|                                                                  |
|   +---------------------------------------+                      |
|   | MI300X capacity (sovereign-region)     |                      |
|   +---------------------------------------+                      |
|                  ^                                                |
|                  |                                                |
|   +---------------------------------------+                      |
|   | Verixa deployment                      |                      |
|   | - Customer's managed Kubernetes        |                      |
|   |   service (EKS / AKS / GKE / OpenShift)|                      |
|   | - Cloud-native Postgres (RDS / Cloud   |                      |
|   |   SQL / Azure Database)                |                      |
|   | - Cloud object store (S3 / Azure Blob /|                      |
|   |   GCS) with customer-managed keys      |                      |
|   +---------------------------------------+                      |
|                                                                  |
+------------------------------------------------------------------+
```

**Customer responsibilities:**
- Cloud account, region selection, sovereign-region commitment
- Managed Kubernetes service lifecycle
- Cloud-native Postgres (typically managed)
- Cloud object store with customer-managed encryption keys
- Cloud IAM federation to corporate IAM
- Cloud KMS or Vault deployment
- MI300X capacity provisioning in cloud account
- Network architecture (VPC, subnets, security groups, peering, transit)

**Verixa responsibilities:**
- Application deployment and operation
- Application updates and patches
- Triad reviewer model deployment on MI300X
- Compliance Dossier rendering
- Customer Success engagement

**Use case fit:**
- Customers with established private-cloud strategy and sovereign-region commitment
- Mid-to-large enterprises with cloud-first AI infrastructure
- Customers with multi-cloud strategy (Verixa cross-cloud)

**Operational SLA:**
- Verixa software support: 99.9% application availability
- Cloud provider's underlying infrastructure SLA applies
- Joint incident response runbook with cloud provider escalation paths

---

## 4. Sovereign managed topology (Tier 3 — Verixa-operated dedicated tenancy on AMD Developer Cloud)

```text
+----------------------------------------------------------------+
|             Verixa-Operated Dedicated Tenancy                    |
|             on AMD Developer Cloud                               |
|                                                                  |
|   +---------------------------------------+                      |
|   | Single-tenant infrastructure           |                      |
|   | - No multi-tenant overlap              |                      |
|   | - Per-customer network isolation       |                      |
|   | - Per-customer Vault namespace          |                      |
|   | - Per-customer object-store prefix      |                      |
|   |   with customer-supplied or             |                      |
|   |   Verixa-managed keys                   |                      |
|   +---------------------------------------+                      |
|                                                                  |
|   +---------------------------------------+                      |
|   | Dedicated MI300X capacity              |                      |
|   | - Sized to customer workload           |                      |
|   | - Triad reviewer models always-on      |                      |
|   +---------------------------------------+                      |
|                  ^                                                |
|                  |                                                |
|   +---------------------------------------+                      |
|   | Verixa-managed Verixa stack            |                      |
|   | - Verixa-operated Kubernetes            |                      |
|   | - Verixa-operated Postgres HA           |                      |
|   | - Verixa-operated object store          |                      |
|   | - Verixa-operated SPIRE                 |                      |
|   | - Verixa-operated Vault per-tenant      |                      |
|   |   namespace                             |                      |
|   +---------------------------------------+                      |
|                                                                  |
|   +---------------------------------------+                      |
|   | Customer-controlled access              |                      |
|   | - OIDC / SAML federation                |                      |
|   | - VPN or dedicated tunnel option        |                      |
|   | - Webhook destinations to customer SIEM |                      |
|   +---------------------------------------+                      |
|                                                                  |
+------------------------------------------------------------------+
```

**Customer responsibilities:**
- IAM federation to Verixa Control Plane (OIDC / SAML)
- Webhook destination configuration
- Sovereign-data sign-off for the dedicated tenancy contract
- Customer integration consumer (no infrastructure ownership)

**Verixa responsibilities:**
- Full-stack infrastructure operation
- 24/7 SRE coverage
- Application + infrastructure updates and patches
- MI300X capacity planning and operation
- Vault and signing key operation (with customer-managed key option for highest-tier customers)
- Backup and disaster recovery
- Compliance Dossier rendering
- SOC 2 / ISO 27001 / ISO 42001 attestation maintenance

**Use case fit:**
- Regulated mid-market enterprises that want sovereign deployment without infrastructure ownership
- Customers who want operational simplicity but need single-tenant data isolation
- Customers in regulated sectors who don't have on-premises capacity but cannot use multi-tenant SaaS

**Operational SLA:**
- 99.5% application availability
- 24/7 SRE coverage
- Premium support add-on extends to 99.95% with extended SLA

---

## 5. Hosted SaaS topology (Tier 4 — multi-tenant)

```text
+----------------------------------------------------------------+
|         Verixa-Operated Multi-Tenant on AMD Developer Cloud      |
|                                                                  |
|   +---------------------------------------+                      |
|   | Multi-tenant infrastructure            |                      |
|   | - Per-tenant Postgres database          |                      |
|   | - Per-tenant object-store prefix         |                      |
|   | - Per-tenant Vault namespace             |                      |
|   | - Per-tenant SPIFFE trust domain         |                      |
|   | - Postgres row-level security as         |                      |
|   |   defence-in-depth                       |                      |
|   +---------------------------------------+                      |
|                                                                  |
|   +---------------------------------------+                      |
|   | Shared MI300X reviewer pool            |                      |
|   | - Tenant-aware scheduling                |                      |
|   | - Per-tenant rate limits                 |                      |
|   | - No tenant data leak across reviewers   |                      |
|   |   (per-decision request envelope)        |                      |
|   +---------------------------------------+                      |
|                                                                  |
|   +---------------------------------------+                      |
|   | Customer integration                   |                      |
|   | - OIDC / SAML federation per tenant    |                      |
|   | - Webhook destinations per tenant      |                      |
|   | - Tenant-scoped API keys / SDKs         |                      |
|   +---------------------------------------+                      |
|                                                                  |
+------------------------------------------------------------------+
```

**Customer responsibilities:**
- IAM federation
- Webhook destination configuration
- Customer integration consumer

**Verixa responsibilities:**
- Full-stack infrastructure operation
- Multi-tenant isolation
- 24/7 SRE coverage
- All updates, patches, certifications

**Use case fit:**
- Mid-market customers
- Lower-risk internal AI workflows
- Departmental deployments below the regulated-data threshold
- Customers evaluating Verixa before sovereign deployment

**Operational SLA:**
- 99.9% application availability
- Standard support hours; premium support add-on for 24/7

---

## 6. Cross-topology architectural consistency

Critical architectural property: **the same Verixa codebase deploys to all four topologies without code changes.** Differences are configuration, operational ownership, and tenancy model.

This matters because:
- Security review, audit, and certification done for one topology applies to all four
- Customer migration between topologies (e.g. Tier 4 → Tier 3 → Tier 1 over time) requires only data migration, not application re-architecting
- Verixa engineering investment is amortised across all topologies; no per-topology forking
- Bug fixes and security patches roll out to all topologies on the same release cadence

Configuration delta per topology:
- IAM provider configuration (customer IdP vs Verixa-operated)
- Vault backend (customer Vault vs Verixa Vault)
- Object store backend (customer S3 vs MinIO vs Verixa S3 vs cloud-native)
- Postgres deployment (customer-managed vs cloud-managed vs Verixa-managed)
- SPIRE root CA (customer-rooted vs Verixa-rooted vs federated)

---

## 7. Sizing guidance

| Customer scale | Governed actions/sec (peak) | MI300X count (Triad reviewer pool) | Postgres node count | Recommended topology |
|---|---|---|---|---|
| Small mid-market | < 10 | 1–2 (mixed reviewer sizes) | 1 + 1 replica | Tier 4 Hosted SaaS |
| Mid-market regulated | 10–50 | 2–4 | 1 primary + 2 replicas | Tier 3 Sovereign Managed |
| Tier 2 bank / regional | 50–200 | 4–8 | 1 primary + 2 replicas + warm archive | Tier 1 / 2 Enterprise |
| Tier 1 bank / large enterprise | 200–1000+ | 8–32 | Sharded primary + multi-region replicas | Tier 1 Enterprise on-prem |
| Public sector / defence | varies, often spiky | 4–16 (peak-scaled) | 1 primary + 2 replicas | Tier 1 on-prem |

Sizing is calibrated per customer at pilot; production sizing reviews quarterly.

---

## 8. Migration paths

Customers can migrate between topologies as their AI deployment matures.

| From | To | Migration effort | Typical trigger |
|---|---|---|---|
| Tier 4 Hosted SaaS | Tier 3 Sovereign Managed | Data migration; Verixa-led; ~2 weeks | Workload moves into regulated scope |
| Tier 3 Sovereign Managed | Tier 1 / 2 Enterprise | Data migration + customer infrastructure setup; ~6–12 weeks | Customer brings infrastructure on-prem |
| Tier 2 (private cloud) | Tier 1 (on-prem) | Data migration + on-prem infrastructure setup; ~8–16 weeks | Sovereignty mandate strengthens |
| Tier 1 (on-prem) | Tier 2 (private cloud) | Data migration + cloud setup; ~6–10 weeks | Customer cloud strategy shift |

Migration retains audit ledger continuity (hash chain preserved across migration); replay vault snapshots are re-keyed if customer key hierarchy changes.

---

## 9. Disaster recovery topology

Each topology has a documented DR pattern:

- **Tier 1 / 2:** customer-led DR; Verixa supports with documented backup/restore runbooks; RTO 1 hour, RPO 5 minutes (configurable per customer)
- **Tier 3:** Verixa-led DR; primary tenant in primary AMD Developer Cloud region, warm DR tenant in secondary region; RTO 30 minutes, RPO 1 minute
- **Tier 4:** Verixa-led DR; multi-region active-passive; RTO 1 hour, RPO 5 minutes

DR testing cadence: annual full DR test for Tier 3 / 4; customer-led DR testing supported and welcomed for Tier 1 / 2.

---

## 10. Procurement-ready deployment artefacts

For each topology, Verixa provides during procurement:

- **Reference architecture diagram** (this document plus customer-specific tailoring)
- **Sizing worksheet** (governed actions/sec → MI300X + Postgres + storage sizing)
- **Network requirements specification** (ports, protocols, egress rules, ingress rules)
- **IAM federation guide** (OIDC / SAML setup with major IdP vendors)
- **Backup and DR runbook** (tailored per topology)
- **Helm chart values reference** (Tier 1 / 2 deployments)
- **Security architecture document** (linked from this pack)
- **Threat model** (linked from this pack)

---

*This Deployment Topology document is the canonical infrastructure reference for Verixa. The System Architecture Document defines the architectural surface; this document specifies how it is deployed across customer environments. The Security Architecture document specifies the security controls per topology. The Build Plan defines the phased delivery of topology support. Updates require Chief Architect + Customer Success Lead approval.*
