# Verixa — Incident Response Plan

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: Verixa SRE + Security teams, customer's CISO + IR team, Big 4 advisor, regulator-facing audit team

---

## 1. Purpose

This document is Verixa's standalone Incident Response Plan (IRP). It specifies how Verixa identifies, contains, eradicates, and recovers from security and operational incidents, and how Verixa coordinates incident response with customers, sub-processors, and regulators.

It complements (does not replace):
- **SRE & Operations** document — operational reliability and routine incident handling
- **Threat Model** — what we're defending against
- **Security Architecture** — the controls being defended
- **Data Protection & Privacy** — personal data breach notification specifics

This is a procurement-grade artefact. Customer security teams use it to assess Verixa's incident readiness during procurement and to align customer-side IR with Verixa's IR during ongoing operation.

---

## 2. Scope

This IRP covers:

- **Security incidents** — unauthorised access, data exposure, malicious activity, supply chain compromise
- **Operational incidents** — outages, data integrity issues, service degradation
- **Compliance incidents** — audit ledger integrity violation, replay vault corruption, evidence-pack generation failure under regulatory deadline
- **Personal data breaches** — per UK / EU GDPR Article 33–34

The IRP applies to all Verixa deployment topologies (Tier 1–4). Customer-environment-specific responsibilities differ by topology and are documented per topology in §6.

---

## 3. Incident definitions and severity

### 3.1 Severity classification

Aligned with industry standard, calibrated for Verixa's regulated-runtime context:

**S1 — Critical**
- Verixa runtime down or fundamentally compromised
- Audit Ledger integrity violated or threatened
- Replay Vault corruption affecting customer evidence
- Data exposure incident (any customer personal data exposed outside customer trust boundary)
- Active malicious activity in Verixa-controlled environment
- Compromise of Verixa signing keys, encryption keys, or customer-managed key infrastructure

**S2 — High**
- Significant degradation of Runtime Gateway, Triad Review, or Audit Emit
- Loss of capability (e.g. Triad reviewer pool unavailable)
- SLO breach in progress with customer impact
- Suspected (unconfirmed) security incident
- Webhook delivery failures persisting > 1 hour to customer SIEM/ITSM
- Compliance Dossier generation blocked under regulator deadline pressure

**S3 — Medium**
- Degraded but functioning system
- Non-critical SLO breach
- Localised performance issue
- Single-customer integration issue
- Discovered vulnerability with available mitigation

**S4 — Low**
- Minor issue with no immediate customer impact
- Cosmetic UI issue
- Documentation discrepancy
- Vulnerability in non-critical path with deferred mitigation

### 3.2 Examples of categorised incidents

| Scenario | Severity |
|---|---|
| Audit Ledger hash chain integrity check fails | S1 |
| Postgres primary down with replica failover successful | S2 (S1 if replica also fails) |
| Reviewer model unavailable, fall-back to two-of-three | S2 |
| Reviewer pool entirely down | S1 |
| Webhook delivery 5% failure rate over 30 minutes | S3 |
| Webhook delivery 100% failure rate (customer SIEM down) | S2 (escalates if persists) |
| Single agent identity rate-limited | S4 |
| All agents in workflow rate-limited (customer fault) | S3 |
| All agents rate-limited (Verixa fault) | S2 |
| Replay query returning incorrect bundle | S1 |
| Replay query slow (within tier-down tolerance) | S3 |
| Cosign signature verification fails on container image | S1 (deployment blocked) |
| Suspected prompt injection through customer's primary agent | S2 (customer notified, joint investigation) |
| Confirmed unauthorised access to Verixa control plane | S1 |
| Confirmed unauthorised access to customer's data via Verixa | S1 |

---

## 4. Incident response process

### 4.1 Six-phase process

Verixa's IR follows a six-phase model:

```
[Preparation]
     |
     v
[Detection] ----> [Triage] ----> [Containment]
                                       |
                                       v
                                 [Eradication]
                                       |
                                       v
                                  [Recovery]
                                       |
                                       v
                              [Post-Incident Review]
                                       |
                                       v
                              [Preparation+ feedback loop]
```

### 4.2 Phase definitions

**Preparation (continuous, not incident-specific):**
- Runbooks maintained and tested
- IR team rosters maintained
- IR tooling available (forensic capture, secure communication channels)
- Annual IR tabletop exercises
- Quarterly chaos and resilience tests (per SRE & Operations document §8)
- Customer IR contact directory maintained per Tier 2/3/4 customer

**Detection:**
- Automated: Prometheus alerts on SLO breach; Verixa-internal SIEM alerts on suspicious activity; integrity check failures on Audit Ledger
- Manual: customer report; Verixa staff observation; security advisory monitoring; threat intelligence
- All detected anomalies enter the triage queue with timestamp + detection source

**Triage:**
- On-call SRE or security engineer first-responds within tier-specific SLA (see §5)
- Confirms incident vs false positive
- Assigns initial severity
- Spins up incident channel (Slack / Teams / equivalent)
- Notifies appropriate stakeholders per severity

**Containment:**
- Short-term: stop the bleeding (e.g. block the affected agent, isolate the affected component, activate degraded mode)
- Long-term: stable mitigation while investigating
- Communication: customer notification per severity SLA

**Eradication:**
- Root cause identified
- Vulnerability patched, malicious artefact removed, configuration corrected
- Forensic evidence captured before eradication where applicable

**Recovery:**
- Affected services restored to normal operation
- Validation that incident is fully resolved
- Customer-facing recovery confirmation
- Operational metrics back within SLO

**Post-Incident Review (PIR):**
- Within 5 business days for S1/S2
- Timeline reconstruction
- Root cause analysis
- Customer impact accounting
- Mitigation actions taken
- Preventive actions (engineering, operational, process)
- Customer-facing summary
- Lessons-learned feedback into Preparation phase

### 4.3 Incident command structure

For any S1 or S2 incident:

- **Incident Commander (IC):** senior SRE or Security Architect; owns the response, makes decisions
- **Operations Lead:** focused on containment, eradication, recovery
- **Communications Lead:** focused on customer + internal communication
- **Scribe:** maintains incident timeline in real-time
- **Subject Matter Experts (SMEs):** rotated in based on incident specifics (e.g. database engineer, security engineer, ML engineer for reviewer-model incident)

For S3 / S4 incidents, SRE on-call handles end-to-end without formal incident command.

---

## 5. Response SLAs

### 5.1 Internal first-response SLA

| Severity | First response | Status update cadence |
|---|---|---|
| S1 | 15 minutes (24/7 for Tier 3/4) | Every 30 minutes during active response |
| S2 | 30 minutes (24/7 for Tier 3/4) | Every 60 minutes |
| S3 | 4 hours (business hours for Tier 1/2) | Daily |
| S4 | Next business day | Weekly |

### 5.2 Customer notification SLA

| Severity | Customer notification |
|---|---|
| S1 | Within 4 hours of detection |
| S2 | Within 12 hours of detection |
| S3 | Within 48 hours of detection |
| S4 | In monthly operational review |

For confirmed personal data breaches, the Data Protection & Privacy document §14 commitment of 24-hour notification to customer DPO applies, regardless of the operational severity classification (which may be different from the privacy-impact classification).

### 5.3 Resolution targets

Resolution targets are stated as targets, not contractual commitments (commitments live in the SLA schedule of the customer agreement):

| Severity | Target resolution |
|---|---|
| S1 | 4 hours |
| S2 | 12 hours |
| S3 | 5 business days |
| S4 | 30 days |

---

## 6. Topology-specific responsibilities

### 6.1 Tier 1 — On-premises

- **Customer responsibilities:** infrastructure-layer detection (network, host, hardware), customer-side log forwarding to customer SOC, customer-side IR activation per their own IR plan
- **Verixa responsibilities:** application-layer detection, Verixa-side log forwarding, joint IR collaboration, application-layer containment / eradication / recovery
- **Joint:** post-incident review for incidents affecting Verixa application

### 6.2 Tier 2 — Private cloud

- **Customer responsibilities:** cloud-account-level detection, customer SOC integration, customer-side IR activation
- **Verixa responsibilities:** application-layer detection and IR
- **Joint:** post-incident review for incidents affecting Verixa application
- **Cloud provider responsibilities:** cloud-platform-layer detection per cloud provider's IR plan; customer escalates to cloud provider as needed

### 6.3 Tier 3 — Sovereign managed

- **Verixa responsibilities:** full-stack IR — infrastructure, application, security, recovery
- **Customer responsibilities:** customer-side decision-making (e.g. authorise communications), customer-side coordination with their own IR, regulatory notification
- **AMD Developer Cloud responsibilities:** cloud-platform-layer detection and remediation per AMD's IR posture

### 6.4 Tier 4 — Hosted SaaS

- **Verixa responsibilities:** full-stack IR
- **Customer responsibilities:** customer-side decision-making, customer-side IR for their integration
- **AMD Developer Cloud responsibilities:** as Tier 3

For multi-customer incidents (incidents affecting multiple customers simultaneously), Verixa coordinates customer-by-customer notification while preserving cross-customer confidentiality.

---

## 7. Specific incident playbooks

### 7.1 Audit Ledger integrity violation

**Trigger:** Hash-chain integrity check fails for any tenant.

**Immediate response:**
1. **Containment:** freeze writes to affected tenant's audit ledger; redirect new writes to incident-quarantine ledger
2. Alert IC + Security Architect + customer's named technical contact
3. **Forensic capture:** snapshot affected ledger state; preserve all logs around the timeframe of the failed integrity check
4. **Investigation:** walk the chain to identify the failing entry; determine whether tampering occurred or whether a software defect produced the failure
5. **Customer notification:** within 4 hours (S1)

**Recovery:**
- If software defect: identify, patch, re-validate chain integrity, resume normal writes
- If tampering: full security incident response (§7.5); regulator notification consultation with customer

**Post-incident:**
- PIR with customer + Big 4 advisor (where customer engages)
- Preventive: review hash-chain implementation, key rotation procedures, write-path access controls

### 7.2 Replay Vault corruption

**Trigger:** replay job returns incorrect bundle, or bundle integrity check fails.

**Immediate response:**
1. **Containment:** mark affected bundle(s) as corrupted; block replay queries on affected bundles
2. Alert IC + Customer Success
3. **Forensic capture:** snapshot affected object-store state; preserve all metadata around the bundle
4. **Investigation:** determine whether corruption is local (single bundle), tenant-wide, or systemic; cross-reference with Audit Ledger entries
5. **Customer notification:** within 12 hours (S2; S1 if affecting active regulator engagement)

**Recovery:**
- If single bundle: assess recoverability from cross-region replica; if irrecoverable, document for Audit Ledger reference
- If systemic: full Verixa-side IR; engage cross-region replication for affected tenant
- Customer impact assessment in writing

### 7.3 Reviewer model unavailable

**Trigger:** one or more reviewer models in Triad pool fails health check or returns persistent timeouts.

**Immediate response (single reviewer down):**
1. **Containment:** Triad falls back to two-of-three per disagreement policy
2. Operational alert; no customer notification required unless persistent > 1 hour
3. **Investigation:** GPU health, vLLM service health, model artefact integrity

**Immediate response (two or three reviewers down):**
1. **Containment:** Triad falls back to single-reviewer or human-review-mandatory per policy
2. Customer notification (S2; S1 if Tier 1 customer with strict triad SLA)
3. **Recovery:** restore reviewer pool from MI300X capacity reserves or scheduling backoff

### 7.4 Customer IAM (OIDC) outage

**Trigger:** customer's IdP unreachable; Control Plane authentications failing.

**Immediate response:**
1. **Containment:** cached IAM tokens with short TTL allow in-progress sessions; new sessions degraded
2. Operational alert; customer notification (S2 or S3 depending on duration)
3. **Investigation:** confirm whether outage is customer-side or Verixa-side
4. If customer-side: communicate, support customer's IAM IR
5. If Verixa-side: full Verixa IR; engage backup OIDC routing

**Recovery:** customer IAM restored; in-progress sessions resume normally.

### 7.5 Confirmed unauthorised access (S1 security incident)

**Trigger:** confirmed unauthorised access to any Verixa-controlled environment.

**Immediate response:**
1. **Containment:** revoke compromised credentials; isolate affected systems; halt suspect operations
2. Alert IC + Security Architect + Verixa CISO
3. **Forensic capture:** preserve full system state; capture network logs, authentication logs, command history, process snapshots
4. **Customer notification:** within 4 hours (S1)
5. **Personal data breach assessment:** if any customer personal data was exposed, Article 33 / 34 GDPR processes activate (Data Protection & Privacy document §14)

**Eradication:**
- Identify and close the access vector (credential compromise, vulnerability, supply chain)
- Patch / reconfigure / re-key as required
- Verify no persistence mechanisms remain

**Recovery:**
- Restore systems from clean state
- Validate no ongoing unauthorised access
- Customer-validated recovery confirmation

**Post-incident:**
- PIR with customer
- Regulator coordination via customer (customer is Controller; Verixa supports their regulator notification)
- External post-incident report by independent security firm where customer requires
- Lessons-learned feedback to threat model and security architecture

### 7.6 Supply chain compromise

**Trigger:** Cosign signature verification fails, or vulnerability discovered in pinned dependency, or upstream signed artefact found compromised.

**Immediate response:**
1. **Containment:** block deployment of affected artefacts; revert to last-known-good
2. Alert IC + Security Architect
3. **Investigation:** scope (which artefacts, which deployments, which customers); root cause (build pipeline, dependency, signing key)
4. **Customer notification:** S2 (S1 if any deployments include compromised artefact)

**Eradication:**
- Re-build artefacts from clean source
- Re-sign with rotated keys if signing infrastructure is implicated
- Validate via reproducible build

**Recovery:**
- Phased rollout of clean artefacts
- Customer-validated recovery
- Verifiable provenance attestation re-issued

### 7.7 Compliance dossier generation failure under regulator deadline

**Trigger:** customer reports regulator-deadline pressure with dossier generation failing.

**Immediate response:**
1. **Triage:** S2 minimum (S1 if customer reports imminent regulator escalation)
2. Engineering on-call + Customer Success engaged
3. **Investigation:** root cause of dossier generation failure
4. **Mitigation:** parallel manual evidence assembly using audit ledger query + replay vault retrieval as fallback if generation cannot be fixed in time
5. **Customer support:** Verixa staff on-bridge with customer through regulator window

**Recovery:**
- Dossier delivered, manually-assembled if necessary
- PIR including process improvement to prevent recurrence
- Engineering bug-fix in dossier generation pipeline

---

## 8. Communication during incidents

### 8.1 Customer communication channels

- **Tier 3/4 customers:** dedicated Slack / Teams channel for incident updates (customer-elected)
- **Tier 1/2 customers:** customer's chosen channel — email, bridge call, or established secure communication
- **All customers:** status page (Verixa-operated) with anonymised incident status for systemic incidents
- **Status page URL:** documented in Customer Success welcome materials

### 8.2 Internal communication

- **Incident channel:** dedicated Slack / Teams channel per incident
- **Incident document:** real-time scribe document; final timeline + RCA committed to incident archive
- **Executive notification:** S1 incidents reach Verixa CISO + CTO + CEO within 30 minutes; S2 within 2 hours

### 8.3 External communication

- **Regulator notification:** customer (as Controller) notifies their supervisory authority; Verixa supports
- **Public disclosure:** material vulnerabilities disclosed via security advisory after coordinated disclosure window (typically 90 days)
- **Bug bounty / coordinated disclosure:** Phase 2+ formal programme; until then, security@verixa inbox

---

## 9. Forensic capture and evidence preservation

For any S1 or S2 security incident:

- **System state snapshot:** affected hosts, processes, network state at time of detection
- **Log preservation:** all logs around the incident timeframe preserved with chain-of-custody documentation
- **Memory capture:** where applicable and not destructive to investigation
- **Network capture:** affected network segments
- **Audit Ledger excerpt:** relevant audit ledger entries with hash-chain proof

Forensic evidence is preserved in a tamper-evident archive with documented chain of custody. Available to customer + regulators on request via the customer's contractual route.

---

## 10. Personal data breach response (Article 33 / 34 GDPR)

For any incident involving suspected personal data breach:

1. **Privacy lead activated** alongside security IR
2. **Initial assessment:** is personal data affected, of what categories, of what data subjects, in what way
3. **Customer DPO notification within 24 hours** (per Data Protection & Privacy document §14)
4. **Joint assessment** with customer of Article 33 notifiability
5. **Customer notifies supervisory authority within 72 hours** (Article 33)
6. **Affected data subjects notified by customer where required** (Article 34)
7. **Joint regulator engagement** if requested

Verixa's role is to support customer's notification obligations with full and timely information; the customer (as Controller) makes the regulator and data subject notification.

---

## 11. Regulator coordination

### 11.1 Verixa direct regulator engagement

Verixa engages directly with regulators in three scenarios:
- Customer-invited regulator engagement (Verixa joins customer + regulator meeting)
- Verixa-as-subject regulator inquiry (e.g. CSA, NIST, ISO/IEC SC 42 standards-body engagement)
- Cross-customer incident with platform-level regulator interest

### 11.2 Customer-led regulator engagement

For incidents where customer is the regulated entity (typical for high-risk AI deployment incidents), the customer leads regulator engagement and Verixa supports:
- Technical evidence (audit ledger excerpts, replay reconstructions, Compliance Dossier)
- Subject matter experts on-bridge
- Written supporting statements where requested

---

## 12. IR drills and tabletop exercises

### 12.1 Annual full IR drill

- **Tier 3 / 4:** annual full IR drill simulating S1 incident end-to-end
- **Tier 1 / 2:** customer-led drill with Verixa participation as needed
- **Cross-customer:** annual drill simulating multi-customer platform-level incident

### 12.2 Quarterly tabletop exercises

- **Internal:** Verixa SRE + Security teams + leadership
- **Scenarios:** rotated across the playbooks in §7
- **Outputs:** runbook updates, tooling improvements, training gaps identified

### 12.3 Customer-invited tabletop

Customer can invite Verixa to participate in customer-side IR tabletops. Verixa attends to align cross-organisational IR.

---

## 13. Lessons learned and continuous improvement

Every PIR feeds back into:

- **Runbook updates** — refined or new runbooks added to SRE & Operations document
- **Threat Model updates** — new threats incorporated; existing threat severity recalibrated
- **Security Architecture updates** — control changes if needed
- **Engineering work** — preventive engineering tickets prioritised
- **Operational tooling** — IR tooling improvements
- **Training** — staff training topics identified

Lessons-learned register is maintained by Security Architect; reviewed quarterly with engineering and SRE leadership.

---

## 14. Document maintenance

This Incident Response Plan is reviewed:

- After every S1 or S2 incident
- After every annual IR drill
- After any material threat model update
- Annually as scheduled review
- On any regulatory or standards-body change affecting IR practice

Reviews sign-off: Verixa CISO + SRE Lead + Security Architect.

---

*This Incident Response Plan is the canonical IR reference for Verixa. The SRE & Operations document covers routine operational handling; this document covers incident-grade response. The Threat Model and Security Architecture documents specify the threat and control surfaces. The Data Protection & Privacy document covers personal data breach specifics. Updates require CISO + SRE Lead approval.*
