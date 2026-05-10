# Verixa — Data Protection & Privacy

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: Customer DPO, Verixa DPO, procurement officer, Big 4 privacy advisor

---

## 1. Purpose

This document specifies how Verixa handles personal data and meets data-protection obligations under UK GDPR, EU GDPR, and sector-specific privacy frameworks. It is the canonical reference the customer's Data Protection Officer (DPO) uses to:

- Assess Verixa as a sub-processor / processor in their data flow
- Complete a Data Protection Impact Assessment (DPIA) where required
- Negotiate a Data Processing Agreement (DPA) with Verixa
- Respond to data subject rights requests (access, erasure, portability, etc.)
- Demonstrate to a regulator that Verixa is a compliant component of the customer's AI deployment

This document is a procurement-grade artefact paired with the legal DPA template (separate document under contract).

---

## 2. Roles and responsibilities under GDPR

### 2.1 The roles

In a typical Verixa deployment:

- **Customer = Data Controller** for the personal data of their data subjects (their customers, employees, citizens, patients, etc.)
- **Verixa = Data Processor** acting on behalf of the customer
- **AMD Developer Cloud (Tier 3 / 4) = Sub-processor** providing infrastructure
- **Customer's primary AI model providers = Sub-processors** of the customer (not of Verixa)

Verixa never acts as a Data Controller on customer-supplied data. Verixa is a Data Controller only for limited Verixa-specific data (e.g. customer admin user account information).

### 2.2 Customer responsibilities

- Determining lawful basis for processing personal data through AI systems governed by Verixa
- Providing privacy notices to data subjects
- Conducting DPIAs for high-risk processing (which AI agentic processing typically is)
- Establishing data retention policies aligned to lawful basis
- Responding to data subject rights requests (Verixa supports the response; customer is the controller)
- Notifying regulators of personal data breaches per Article 33 of UK / EU GDPR

### 2.3 Verixa responsibilities

- Acting only on documented customer instructions (the DPA is the documented instruction set)
- Implementing technical and organisational measures (TOMs) per Article 32 GDPR
- Notifying the customer of personal data breaches affecting customer data without undue delay (target: within 24 hours of detection)
- Supporting customer in responding to data subject rights requests
- Supporting customer in DPIAs by providing this document and the Threat Model
- Engaging sub-processors only with customer's prior agreement
- Returning or deleting customer personal data at end of contract per customer's instruction

---

## 3. Data flows and categories

### 3.1 Personal data Verixa may process

Verixa processes personal data on behalf of the customer in the following categories:

| Category | Source | Where stored | Retention |
|---|---|---|---|
| Customer's data subjects' identifiers in retrieved documents | Customer's primary AI workflow | Replay Vault snapshots (encrypted) | Per customer DPA |
| Customer's data subjects' identifiers in tool arguments | Customer's primary AI workflow | Replay Vault snapshots (encrypted), Audit Ledger (referenced, not stored verbatim where possible) | Per customer DPA |
| Customer's data subjects' identifiers in agent-stated claims | Customer's primary AI workflow | Replay Vault snapshots | Per customer DPA |
| Customer's reviewers' identifiers | Customer IAM | Audit Ledger, Human Review records | 7 years default; per regulatory cadence |
| Customer's policy authors' identifiers | Customer IAM | Policy registry | Lifetime of customer engagement |
| Customer admin users' authentication metadata | Customer IAM via OIDC/SAML | Verixa session store | Session-bound; cached IAM tokens 15-minute TTL |

### 3.2 Personal data Verixa does NOT process (typically)

- Customer's data subjects' raw biometric data (Verixa is not a biometric processor)
- Customer's data subjects' health records (unless stored as references in retrieved documents — and even then, redaction-friendly handling)
- Customer's payment card data (Verixa is explicitly out-of-scope for PCI-DSS regulated data flows; customer must redact card data before Verixa sees it)

If a customer's AI workflow involves these data categories, joint DPA review specifies handling per category.

### 3.3 Data flow diagram (canonical)

```text
[Customer's Data Subject]
         |
         | (data subject's information becomes part of customer's business processing)
         v
[Customer's Primary AI Agent]
         |
         | retrieves documents, calls tools, generates outputs
         v
[Verixa Runtime Gateway] ← Verixa here as Data Processor
         |
         | governs the action, records audit + replay
         v
[Customer's Tools / Systems] ← acts on data subject's data
         |
         v
[Customer's Compliance + Audit + Regulator]
```

Verixa's involvement starts at the Runtime Gateway and ends at evidence delivery. Verixa never:
- Trains models on customer data
- Repurposes customer data for any purpose other than governance and evidence
- Shares customer data with third parties (other than customer-authorised webhook destinations)
- Aggregates customer data across customers (cross-tenant analytics are not part of Verixa)

---

## 4. Lawful basis support

Verixa supports the customer's lawful basis under Article 6 (and Article 9 / 10 for special category data):

- **Performance of contract** — typical for B2B AI workflows
- **Legitimate interest** — typical for fraud detection, anti-money-laundering AI workflows
- **Legal obligation** — typical for regulatory reporting AI workflows
- **Public task** — typical for public sector AI workflows
- **Consent** — typical for customer-facing AI assistants where data subject consent is obtainable

Verixa as Data Processor does not determine lawful basis; the customer does. Verixa's role is to govern the resulting processing in line with the customer's documented instructions.

For special category data (Article 9 — health, ethnicity, biometrics, etc.), additional Article 9 safeguards are required. Verixa supports these via the customer's compliance pack (e.g. healthcare compliance pack with MHRA / EU MDR alignment).

---

## 5. Technical and organisational measures (TOMs)

Verixa's TOMs implement Article 32 GDPR requirements. Detail is in the Security Architecture document; summary here:

### 5.1 Confidentiality

- Per-tenant encryption of Replay Vault snapshots (AES-256-GCM)
- Per-tenant key hierarchy with customer-managed key option in Tier 1 / 2 / 3
- mTLS between every pair of internal services (SPIFFE/SPIRE)
- Role-Based Access Control (RBAC) at Control Plane API
- Customer IAM federation (OIDC / SAML) for human authentication
- Multi-Factor Authentication required for production environment access
- Verixa staff cannot decrypt Replay Vault bundles in Tier 1 / 2 / 3 (customer-managed key hierarchy)

### 5.2 Integrity

- Hash-chained, Ed25519-signed Audit Ledger
- Content-addressable Replay Vault snapshots
- Signed OCI container images (Cosign)
- Signed Rego policy bundles
- Webhook payload signatures
- Triad commit-and-reveal cryptographic protocol

### 5.3 Availability

- Per-tier availability SLOs (99.5% — 99.95%)
- Postgres HA with synchronous replication
- Object store native durability
- Documented RTO and RPO per component
- Annual DR drills (Tier 3 / 4)

### 5.4 Resilience

- Documented incident response (Threat Model + SRE & Operations + Incident Response Plan)
- 24/7 SOC for Tier 3 / 4
- Quarterly chaos and resilience testing

### 5.5 Pseudonymisation and minimisation

- Audit Ledger entries reference subject identifiers indirectly where possible (hash references rather than raw identifiers)
- Replay Vault snapshots store full context; subject identifiers redacted on Article 17 erasure via cryptographic-erasure of per-subject keys
- Operational telemetry (Prometheus, traces, logs) does not include subject-identifiable content
- Internal admin operations are themselves audit-ledger entries; subject-identifiable content is not exposed in admin operations

### 5.6 Testing of TOM effectiveness

- Annual third-party penetration testing
- Annual TOM review against the customer's DPIA
- Quarterly internal security control review
- Continuous CVE scanning + patching SLA

---

## 6. Data subject rights

Verixa supports data subject rights through Control Plane operations and customer-facing APIs.

### 6.1 Right of access (Article 15)

Customer's DPO submits subject access request via Control Plane:
1. Subject identifier provided
2. Verixa walks Audit Ledger and Replay Vault for entries containing the subject identifier
3. Output: structured access-request response with all governance records pertaining to the subject
4. Customer's DPO reviews and provides response to data subject

Verixa response to customer's DPO target SLA: 7 days.

### 6.2 Right to rectification (Article 16)

Verixa does not store substantive personal data — it stores governance evidence about processing of personal data by the customer's AI workflow. Rectification is therefore typically the customer's responsibility against the source data systems.

Where audit or replay records contain factually incorrect statements *about* a data subject (e.g. an AI agent's incorrect statement that was governed but recorded), the audit ledger entry remains (regulatory retention) but a corrective annotation can be appended via the Control Plane. The corrective annotation is itself an audit ledger entry.

### 6.3 Right to erasure (Article 17 / "right to be forgotten")

Erasure is **redaction-with-evidence-preservation**, not deletion of audit records. The mechanics:

1. Customer's DPO submits erasure request via Control Plane
2. Verixa identifies all Replay Vault snapshots referencing the subject
3. Verixa cryptographic-erases the per-subject encryption key from Vault; snapshot ciphertext remains but is irrecoverable
4. Audit Ledger entries remain (regulatory retention obligation typically prevails)
5. Erasure receipt issued with cryptographic redaction proof

**Conflict resolution:** Where Article 17 erasure conflicts with Article 18 (10-year retention) or Article 72 (post-market monitoring) obligations, the regulatory retention typically prevails for the audit record while subject-identifiable content is irrecoverable. The DPA governs the conflict resolution per customer-by-customer basis.

Verixa response SLA: 30 days as per GDPR Article 12(3).

### 6.4 Right to restriction of processing (Article 18)

Customer's DPO can flag a subject identifier as "restricted" via Control Plane. Future Verixa governance of actions involving that subject identifier returns a special "restricted_subject" decision class that escalates to human review. Existing audit records remain.

### 6.5 Right to data portability (Article 20)

Verixa's data export is limited to governance evidence about the data subject (the subject's interactions with customer's AI workflow, as governed by Verixa). Format: structured JSON aligned with the Evidence Pack Specification per-subject sub-format.

### 6.6 Right to object (Article 21)

Verixa supports customer's response to objection requests by flagging the subject identifier and ceasing future governance processing of subject-related actions per customer's instruction.

### 6.7 Rights related to automated decision-making (Article 22)

If the customer's AI workflow constitutes automated individual decision-making with legal or significant effects, Article 22 obligations apply. Verixa supports the customer's Article 22 obligations:
- Logging of automated decisions in Audit Ledger
- Replay reconstruction for human review
- Triad Review for high-risk automated decisions
- Approval Matrix for human-in-the-loop where required
- Compliance Dossier output documenting safeguards

The customer determines whether their AI workflow falls under Article 22; Verixa supports either way.

---

## 7. International data transfers

### 7.1 Verixa default posture

In Tier 1 (on-premises) and Tier 3 (sovereign managed in customer's region), customer data does not leave the customer's jurisdiction.

In Tier 2 (private cloud), the customer determines region and the AMD Developer Cloud or other cloud provider's data-residency commitment applies.

In Tier 4 (hosted SaaS), Verixa offers EEA-region tenancy by default for EU/UK customers; customer can elect non-EEA tenancy where appropriate to their use case.

### 7.2 Transfer mechanisms

For any international transfer outside customer's jurisdiction:
- **EU → UK / UK → EU:** UK-EU adequacy decision (currently in force, monitored)
- **EU / UK → US:** EU-US Data Privacy Framework (where applicable) or Standard Contractual Clauses (SCCs)
- **Other transfers:** SCCs as default mechanism

Verixa publishes the relevant SCC modules (Module 2: Controller-to-Processor) as part of the DPA template.

### 7.3 Schrems II compliance

Verixa's sovereign deployment topologies (Tier 1 / 3) are positioned specifically as Schrems II-compliant alternatives to US-cloud processing of EU personal data. Customer's DPIA can lean on Verixa sovereign deployment as a key Schrems II mitigation.

---

## 8. Sub-processor management

### 8.1 Verixa sub-processors

Verixa engages the following sub-processor categories:

- **AMD Developer Cloud** — infrastructure (Tier 3 / 4)
- **HashiCorp Vault** — secrets management (Tier 3 / 4 Verixa-operated; or customer-deployed)
- **Postgres providers** — managed Postgres in cloud topologies (e.g. AWS RDS, Azure Database, Cloud SQL)
- **Object storage providers** — managed object stores in cloud topologies (e.g. AWS S3, Azure Blob, GCS)
- **Identity providers (transit)** — customer's chosen IdP (Okta, Azure AD, Ping, etc.)
- **Penetration testing partners** — contracted annually; named in DPA at customer request

The sub-processor list is maintained as an annex to the DPA and updated on changes.

### 8.2 Sub-processor change notification

- 30 days advance notice to customers of any new sub-processor or change in existing sub-processor
- Customer right to object; Verixa works with customer to find alternative arrangement
- Sub-processor list publicly available; updates dated

### 8.3 Sub-processor contractual flow-down

Every Verixa sub-processor is bound by contract to TOMs at least equivalent to those Verixa commits to in the customer DPA. Verifiable via the sub-processor's own SOC 2 / ISO 27001 / ISO 42001 attestations where relevant.

---

## 9. Data Processing Agreement (DPA) — outline

The DPA is a contractual document executed between Verixa and the customer. This section outlines its structure; the executed DPA is the binding instrument.

### 9.1 DPA structure

1. **Parties and roles** — Verixa as Processor, customer as Controller
2. **Subject matter and duration** — what processing, for how long
3. **Nature and purpose of processing** — runtime governance, audit evidence, replay reconstruction
4. **Categories of personal data and data subjects** — per §3 of this document
5. **Customer's documented instructions** — the substantive scope of permitted processing
6. **Verixa's obligations** — Article 28 obligations + TOMs
7. **Sub-processor management** — list + change notification
8. **Data subject rights support** — per §6 of this document
9. **Personal data breach notification** — within 24 hours
10. **TOMs annex** — cross-references the Security Architecture document
11. **Audit and inspection rights** — customer's right to audit Verixa's compliance
12. **International transfers** — SCCs annex where applicable
13. **End of contract** — return or deletion of customer personal data
14. **Liability** — per master agreement
15. **Governing law and jurisdiction** — customer-jurisdiction default

### 9.2 DPA negotiation posture

Verixa's standard DPA covers most regulated UK / EU enterprise customer requirements without modification. Customer-specific changes typically negotiated:
- Audit and inspection rights specifics (frequency, advance notice, scope)
- Personal data breach notification timing (some customers require shorter than 24-hour SLA)
- Sub-processor pre-approval requirements (some customers require sub-processor pre-approval rather than notification)
- Specific data subject rights response SLAs

Verixa is willing to negotiate; the DPA template is a starting point, not a take-it-or-leave-it.

---

## 10. Privacy by design and default

Verixa is built per the Article 25 GDPR principle of privacy by design and by default:

- **Minimisation:** Verixa processes only the personal data necessary for its governance purpose; subject identifiers are referenced indirectly where possible
- **Default settings:** Default deployment topology is sovereign (Tier 3 dedicated tenancy) rather than multi-tenant; customer must opt into multi-tenant SaaS
- **Pseudonymisation:** Subject identifiers in Audit Ledger are typically references; raw identifiers in Replay Vault are encrypted
- **Encryption at rest and in transit:** AES-256-GCM at rest, TLS 1.3 in transit, mTLS internally
- **Access restrictions:** RBAC + customer IAM + MFA + per-tenant key hierarchy
- **Customer control:** Customer can delete their tenancy at any time, triggering full deletion of customer-specific data per DPA

---

## 11. Privacy notice scaffold

Customer's privacy notice to data subjects typically includes a section on AI governance processing. Verixa provides a scaffold:

> **AI Governance Processing**
> When you interact with our AI-driven services, decisions about your case may be processed through an AI runtime governance platform. The governance platform records the AI's decisions, the policy and risk context of those decisions, and the reviewer outputs (where applicable) for the purpose of:
> (a) ensuring the AI's decisions comply with applicable law and our internal policies
> (b) producing evidence we can review or share with regulators on request
> (c) reconstructing past decisions if required for audit or your inquiry
>
> The governance platform is operated by [Customer Name] using technology provided by Verixa, who acts as our data processor. Verixa does not use your personal data for any purpose other than this governance.
>
> You have rights of access, rectification, erasure, restriction, portability, and objection in relation to this processing. To exercise these rights, contact [Customer DPO].

This is a scaffold; customer's privacy team adapts to their specific notice voice and structure.

---

## 12. Data Protection Impact Assessment (DPIA) support

For customer-led DPIAs, Verixa provides:

- This Data Protection & Privacy document
- The Threat Model document
- The Security Architecture document
- The Regulatory Mapping Matrix
- The Evidence Pack Specification
- Sample DPA
- TOMs evidence
- Most recent SOC 2 / ISO certificates (when available)
- Penetration test executive summary
- Customer-specific consultation with Verixa privacy lead

DPIA content covering Verixa's role:
- Necessity and proportionality of using Verixa for the customer's AI governance
- Risks identified by Verixa Threat Model
- Mitigations per Verixa Security Architecture and TOMs
- Residual risks after mitigation

---

## 13. Records of Processing (Article 30)

Verixa maintains an Article 30 Records of Processing Activities (ROPA) for its role as Processor, available to customer DPOs and regulators on request. Customer maintains their own Article 30 ROPA covering their controller-side processing.

---

## 14. Personal data breach notification

### 14.1 Verixa's notification commitment

Verixa notifies customer's named DPO of any personal data breach affecting customer data without undue delay and in any event within 24 hours of detection. Notification includes:

- Nature of the breach (unauthorised access, accidental disclosure, etc.)
- Categories and approximate volume of personal data affected
- Categories and approximate number of data subjects affected
- Likely consequences
- Measures taken or proposed
- Verixa contact for further information

### 14.2 Customer's regulator notification

Customer is responsible for Article 33 notification to the supervisory authority within 72 hours of becoming aware of a breach. Verixa's 24-hour notification SLA provides customer with up to 48 hours to determine whether the breach is notifiable and prepare the regulator notification.

### 14.3 Joint incident response

For breaches affecting multiple customers (e.g. Verixa platform-level incident), Verixa coordinates customer-by-customer notification while preserving cross-customer confidentiality.

---

## 15. End of contract

At end of contract or per customer instruction:

- **Return:** Customer can request return of customer personal data in structured format (Evidence Pack Specification format)
- **Deletion:** Customer can request deletion; Verixa deletes customer personal data within 30 days
- **Retention beyond contract:** If customer is subject to retention obligations beyond contract end (e.g. Article 18 10-year retention), customer can elect retention with Verixa-archived storage; deletion happens after retention period expires

Verifiable deletion certificate provided on customer request.

---

*This Data Protection & Privacy document is the canonical privacy reference for Verixa. The Data Processing Agreement (DPA) template operationalises the contractual mechanics. The Security Architecture document specifies the TOMs in detail. The Threat Model assesses privacy-relevant risks. Updates require Verixa DPO + Compliance Officer approval and annual review.*
