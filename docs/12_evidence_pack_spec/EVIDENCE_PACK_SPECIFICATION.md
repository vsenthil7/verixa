# Verixa — Evidence Pack Specification

> Enterprise AI runtime control plane and trust platform.
> Document version: 1.0 · Date: 2026-05-10 · Status: Phase 1 baseline · Audience: Compliance officer, Big 4 advisor, regulator-facing audit team, technical reviewer

---

## 1. Purpose

The Evidence Pack is the canonical artefact Verixa emits to satisfy regulator, auditor, and internal-audit information requests on AI system operation. This document specifies:

- The **structure** of an Evidence Pack
- The **generation process** that produces one
- The **integrity guarantees** the pack carries
- The **regulator-acceptance** posture for Annex IV-aligned dossier delivery
- The **lifecycle** of an Evidence Pack (creation, retention, archival, expiry)

The Evidence Pack is what a regulator, auditor, or board risk committee receives when they ask "show me how you governed this AI workflow." It is not generated reactively; it is reconstructed from the audit ledger, replay vault, and policy registry on demand.

---

## 2. Pack types

Verixa emits four distinct pack types. They share a common structure but differ in scope, audience, and inclusion criteria.

### 2.1 Per-decision pack (incident-grade)

- **Trigger:** Regulator question about a specific governed decision; internal audit deep-dive on a specific incident
- **Scope:** A single audit_id with all related context
- **Typical size:** 5–50 MB compressed
- **Generation latency:** Minutes (synchronous from audit ledger + replay vault)
- **Retention:** Bound to the parent audit entry's retention tier

### 2.2 Per-workflow pack (operational-evidence)

- **Trigger:** Regulator question about a workflow's operation over a time range; periodic compliance reporting
- **Scope:** All audit entries for a single workflow over a time range, plus aggregate analytics
- **Typical size:** 50 MB – 5 GB compressed (depending on time range and workflow volume)
- **Generation latency:** Hours (asynchronous; backgrounded Celery job)
- **Retention:** Configurable per regulatory cadence; default 7 years for financial services, 10 years for healthcare/medical-device

### 2.3 Annex IV-aligned technical dossier (regulator-grade)

- **Trigger:** EU AI Act Article 11 / Annex IV technical documentation request; member state authority inspection; conformity assessment
- **Scope:** A complete AI system (one or more workflows scoped together) with full Annex IV section coverage
- **Typical size:** 100 MB – 2 GB compressed; includes PDF deliverable + JSON machine-readable bundle + signed hash chain
- **Generation latency:** Hours to days (depending on time range and section depth)
- **Retention:** 10 years per Article 18

### 2.4 Article 72 post-market monitoring pack (continuous-monitoring-evidence)

- **Trigger:** Article 72 post-market monitoring obligation; periodic regulator reporting; serious incident reporting per Article 73
- **Scope:** Time-bounded performance evidence per AI system, including drift signals, incident lineage, corrective actions
- **Typical size:** 20 MB – 500 MB
- **Generation latency:** Hours (asynchronous)
- **Retention:** 10 years; serious incidents subject to additional regulator-specific retention

---

## 3. Pack structure (canonical)

Every Evidence Pack is delivered as a `.tar.gz` archive with a deterministic internal layout:

```text
verixa-evidence-pack-{pack_id}/
├── manifest.json                    # Pack metadata, integrity proof, ToC
├── README.md                        # Human-readable pack summary
├── 01_pack_summary/
│   ├── pack_summary.pdf             # Executive summary for regulator/auditor
│   └── pack_summary.json            # Machine-readable summary
├── 02_workflow_context/
│   ├── workflow_definition.json     # Workflow registry record
│   ├── agent_definitions.json       # Registered agents involved
│   ├── tool_definitions.json        # Registered tools involved
│   └── model_versions.json          # Model registry records (primary + reviewer)
├── 03_governance_context/
│   ├── policies_applied.json        # Rego policies in effect at pack time-range
│   ├── policy_versions/             # Each policy with full Rego source
│   ├── compliance_packs.json        # Sector compliance packs in effect
│   └── regulatory_mapping.json      # VRX-control to regulatory-obligation crosswalk for this pack
├── 04_audit_evidence/
│   ├── audit_entries.jsonl          # All audit entries in scope (one JSON per line)
│   ├── hash_chain_proof.json        # Hash chain integrity proof with signatures
│   ├── signing_keys.json            # Public keys used to sign entries in scope
│   └── integrity_verification.md    # Human-readable verification instructions
├── 05_replay_evidence/
│   ├── snapshot_index.json          # Index of replay snapshots in scope
│   ├── snapshots/                   # Encrypted snapshot bundles (or references to object store)
│   └── replay_runs/                 # Optional re-execution outputs (for high-significance decisions)
├── 06_review_evidence/
│   ├── triad_reviews.jsonl          # Triad Review records
│   ├── human_reviews.jsonl          # Human Review records (Phase 2+)
│   └── reviewer_disagreements.json  # Highlighted disagreements with resolutions
├── 07_post_market_monitoring/      # (Article 72 packs only)
│   ├── drift_signals.json           # Model Drift Monitor output for time range
│   ├── incident_lineage.json        # Trust Graph incident lineage
│   ├── corrective_actions.json      # Corrective actions taken
│   └── performance_metrics.json     # Operational performance metrics
├── 08_annex_iv_sections/           # (Annex IV dossiers only)
│   ├── 01_general_description.md
│   ├── 02_detailed_description.md
│   ├── 03_monitoring_functioning.md
│   ├── 04_risk_management.md
│   ├── 05_lifecycle_changes.md
│   ├── 06_harmonised_standards.md
│   └── 08_post_market_evaluation.md
├── 09_dossier_pdf/                 # (Annex IV dossiers only)
│   └── annex_iv_technical_dossier.pdf
├── 10_signatures/
│   ├── pack_manifest_signature.txt  # Ed25519 signature of manifest.json
│   ├── tenant_signing_key.pub       # Public key for verification
│   └── verification_instructions.md
└── verifier.sh                       # Standalone shell script for offline verification
```

The structure is consistent across pack types; sections inapplicable to a given pack type are omitted but referenced in manifest.json with status `not_applicable`.

---

## 4. Manifest and integrity proof

`manifest.json` is the integrity anchor of every pack. It contains:

```yaml
pack_id: pack_01J2...
pack_type: annex_iv_dossier
generated_at: 2026-05-10T04:42:11Z
generated_by:
  user: jane.doe@customer.bank
  role: compliance-officer
  authentication_trace: oidc_token_hash_abc123
tenant_id: customer-bank-example
scope:
  workflow_ids: [wf_loan_application_v2]
  time_range_start: 2026-01-01T00:00:00Z
  time_range_end: 2026-04-30T23:59:59Z
  audit_entries_count: 142387
  triad_reviews_count: 8421
  human_reviews_count: 312
contents:
  - section: 01_pack_summary
    file: pack_summary.json
    sha256: abc123...
  - section: 04_audit_evidence
    file: audit_entries.jsonl
    sha256: def456...
    record_count: 142387
  # ... (all sections enumerated)
hash_chain_proof:
  ledger_first_sequence: 12345678
  ledger_last_sequence: 12487965
  first_entry_hash: sha256:...
  last_entry_hash: sha256:...
  chain_integrity_verified: true
  verification_timestamp: 2026-05-10T04:42:09Z
signing:
  pack_signature: ed25519:...
  signing_key_id: key_2026Q2_tenant_customer-bank
  signature_alg: ed25519
verifier_url: https://{tenant}.verixa.example/v1/control/audit/integrity-check?pack_id=pack_01J2...
```

The signature in `signing.pack_signature` is computed over the SHA-256 of the manifest minus the `signing` section itself. Recipients can verify offline by:

1. Removing the `signing` section from manifest.json
2. Computing SHA-256 of the remaining manifest
3. Verifying the signature against the public key in `10_signatures/tenant_signing_key.pub`

Or via online verification at the `verifier_url` if Verixa is reachable.

---

## 5. Hash-chain proof

The `04_audit_evidence/hash_chain_proof.json` artefact provides cryptographic proof that no audit entry in the pack has been tampered with since its original ledger commit. The proof structure:

```yaml
proof_version: 1
ledger_genesis_hash: sha256:...           # Genesis hash for tenant_id
first_in_scope:
  sequence_number: 12345678
  hash_chain_self: sha256:...
  hash_chain_prev: sha256:...
  signature: ed25519:...
  signing_key_id: key_2025Q4_tenant_customer-bank
last_in_scope:
  sequence_number: 12487965
  hash_chain_self: sha256:...
  hash_chain_prev: sha256:...
  signature: ed25519:...
  signing_key_id: key_2026Q2_tenant_customer-bank
in_scope_continuous: true                  # No gaps in sequence between first and last
key_rotations_in_scope:
  - rotated_at: 2026-04-01T00:00:00Z
    from_key: key_2025Q4_tenant_customer-bank
    to_key: key_2026Q1_tenant_customer-bank
    last_sequence_signed_by_old: 12410000
    first_sequence_signed_by_new: 12410001
verification_walk:
  algorithm: sequential_hash_chain_walk
  entries_verified: 142387
  signatures_verified: 142387
  integrity_status: verified
  verified_at: 2026-05-10T04:42:09Z
```

This enables a regulator or external auditor to verify the entire chain of evidence in the pack independently of Verixa, using only the public signing keys and the canonical hash-chain construction algorithm (which is published in the Data Model document).

---

## 6. Generation process

```text
   [Compliance officer in Control Plane UI]
              |
              v
   [Specify pack type, scope, time range]
              |
              v
   [Verixa validates RBAC + policy]
              |
              v
   [Celery job: pack_generate]
              |
              | 1. Query audit ledger by scope predicate
              | 2. Verify hash-chain integrity for all entries in scope
              | 3. Pull policy versions referenced by entries
              | 4. Pull replay snapshots referenced by entries
              | 5. Pull triad and human review records
              | 6. Pull workflow + agent + model registry records
              | 7. Pull drift signals (Article 72) or Annex IV sections
              | 8. Render PDF (Annex IV dossier only)
              | 9. Bundle into tar.gz
              | 10. Sign manifest
              | 11. Upload bundle to object store
              | 12. Emit `dossier.generated` webhook event
              v
   [Bundle ready, downloadable URL with time-bounded access]
              |
              v
   [Compliance officer downloads and delivers to regulator/auditor]
```

The generation process is fully audited; generation events themselves appear in the audit ledger as a special audit_type `pack_generated`.

---

## 7. Regulator-acceptance posture

Verixa positions Annex IV-aligned dossier output as **substantively equivalent** to the technical file format the EU AI Act and member state competent authorities expect. The positioning is deliberately calibrated:

- **What we claim:** Verixa Compliance Dossier output covers the eight Annex IV sections with primary-evidence backing, signed integrity proofs, and machine-readable structured data.
- **What we do not claim:** Verixa cannot pre-certify that any specific regulator will accept any specific dossier on any specific occasion. Regulator acceptance is a regulator decision, not a vendor warranty.
- **What we do support:** customer-led regulator engagement with the Verixa Customer Success team available to brief the regulator on the dossier structure, hash-chain proof, and verification methodology if invited by the customer.

Big 4 advisors and large law firms reviewing Verixa Compliance Dossier output for customer-side AI Act compliance projects are part of the Phase 1 reference programme. Their reviews and any acceptance letters are added to the customer's reference materials.

---

## 8. Retention and lifecycle

Pack retention follows the same tiered model as the Replay Vault (hot / warm / cold), aligned to the most stringent applicable regulation:

| Pack type | Default hot | Default warm | Default cold | Notes |
|---|---|---|---|---|
| Per-decision | 90 days | 1 year | parent audit retention | Inherits from parent audit entry |
| Per-workflow | 90 days | 2 years | 7 years | Financial services default |
| Annex IV dossier | 90 days | 2 years | 10 years | Per Article 18 |
| Article 72 PMM | 90 days | 2 years | 10 years | Per Article 72 + Article 18 |

Sector-specific retention overrides:
- **Healthcare / medical device:** 10–15 years per MHRA / FDA SaMD post-market obligations
- **Defence:** Configurable per customer's operational classification; legal-hold capable
- **Public sector:** Per member state / department-specific retention schedules

Once a pack is in cold storage, restoration to warm or hot is a Control Plane API operation: `POST /v1/control/dossier/{dossier_id}/restore`.

---

## 9. Data subject rights and erasure

Where personal data appears in Replay Vault snapshots referenced by an Evidence Pack, data subject access and erasure requests are handled per the customer's Data Processing Agreement:

- **Subject access requests:** Verixa's Control Plane API supports per-subject queries that walk the audit ledger for entries containing references to the subject and emit a structured access-request response. The audit ledger entries themselves are typically not subject-identifiable; subject identifiers appear in retrieved-document references and tool arguments stored in Replay Vault snapshots.
- **Erasure requests:** Erasure is **redaction-with-evidence-preservation**, not deletion. Subject identifiers are redacted from snapshot bundles via cryptographic erasure (the per-subject encryption key is destroyed); the audit ledger entry remains, demonstrating that the action was governed, but the subject-identifiable content is irrecoverable. This satisfies GDPR Article 17 erasure obligations while preserving the integrity of the audit chain that regulators and auditors require.
- **Conflict of obligations:** Where erasure conflicts with Article 18 / Article 72 retention obligations, the regulatory retention prevails for the audit ledger record while subject identifiers are redacted from snapshots. The DPA governs these conflicts customer-by-customer.

---

## 10. Pack versioning and schema evolution

The Evidence Pack schema is versioned via `manifest.json`'s `pack_schema_version` field. Schema changes:

- **Minor (additive):** new sections or fields added; old packs remain valid; verifier scripts handle missing fields gracefully
- **Major:** breaking changes; old verifiers must be updated; migration documentation provided to customers

The verifier shell script at the root of the pack always verifies the pack against its own embedded schema version. Old packs remain verifiable indefinitely.

---

## 11. Open items for Phase 2+ extension

- **Phase 2:** Approval Matrix Engine adds approval-chain evidence to packs; Human Review Console output integrated; sector compliance pack output formats expanded
- **Phase 3:** Cryptographic timestamp authority integration for additional non-repudiation; long-term signature schemes (LTV-PAdES) for PDF dossier signatures
- **Phase 5:** Hallmark provenance attestation embedded in packs; supplier evidence sharing through Federated Trust Mesh
- **Phase 6:** Cross-org attestation packs for trust-mesh participants

---

*This Evidence Pack Specification is the canonical artefact format reference for Verixa. The Regulatory Mapping Matrix specifies which controls feed which sections. The Data Model specifies the persistent schemas the pack draws from. The System Architecture Document specifies the modules that produce pack content. Updates require Compliance Officer + Chief Architect approval and Phase Gate review.*
