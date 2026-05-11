# ADR-0008 — HashiCorp Vault vs cloud KMS for signing-key custody

- **Status:** Proposed (Phase 1 placeholder)
- **Date:** 2026-05-11
- **Phase:** 1 (production rollout)
- **Decision owner:** TBD at Phase 1 kickoff
- **Affects:** Dossier signing keys, audit ledger anchor keys, per-tenant data encryption keys (DEKs), Phase 0 → Phase 1 key migration

## Context

Phase 0 generates Ed25519 dossier signing keys (ADR-0004) and per-tenant AES-256-GCM DEKs at container start; they live in-process and are lost on restart. The seeded demo regenerates them; real customer data does not have that luxury.

Phase 1 must:

1. **Custody signing keys outside the application process** — process compromise must not reveal keys.
2. **Support per-tenant key isolation** — BR-05 cryptographic erasure works by destroying the per-tenant DEK; that DEK must be deletable on demand.
3. **Survive process restarts** — keys persist across deploys.
4. **Be auditable** — every key use is logged with caller identity (ties into ADR-0007 SPIFFE auth).
5. **Be FIPS 140-3 compatible** for customers in regulated industries (financial services, healthcare, public sector, defence).
6. **Support cross-cloud deployment** (AWS, Azure, GCP, on-premise) without lock-in.

Two candidate technologies:

- **HashiCorp Vault** (or OpenBao, the open fork after IBM's HashiCorp acquisition raised license concerns)
- **Cloud KMS** (AWS KMS / Azure Key Vault / Google Cloud KMS / on-premise HSM)

## Decision (preliminary lean)

**Vault by default; pluggable adapter for cloud KMS as an opt-in for customers who already operate one.**

Implementation: a `KeyCustody` protocol (parallel to ADR-0001 persistence protocols) with two adapters:

- `VaultKeyCustody` — talks to Vault Transit secrets engine over Vault Agent's auto-auth (SPIRE-attested per ADR-0007)
- `KmsKeyCustody` — talks to AWS KMS / Azure Key Vault / GCP KMS via cloud SDK

The runtime is wired against the protocol; the choice is per-deployment via env var.

Final decision deferred to Phase 1 kickoff after design-partner customers tell us their existing key-custody infrastructure.

## Consequences

### Positive

- **Vault is cloud-neutral.** Customers running across AWS + Azure get one operational story.
- **Vault Transit means keys never leave the HSM-backed Vault store.** Application asks Vault to sign/decrypt; key material stays inside.
- **Per-tenant key namespacing** is natural in Vault's path model (`transit/keys/tenant-${tenant_id}/dek`).
- **The pluggable adapter** lets customers who already operate cloud KMS use what they have — no need to introduce Vault as a new operational dependency.
- **OpenBao keeps the option open** if HashiCorp's licensing future becomes problematic (HashiCorp BSL → IBM acquisition raised some adoption concerns for enterprise procurement teams in 2024-2026).

### Negative

- **Two adapters is more code than one.** Maintaining both means double the integration tests, double the failure modes to document.
- **Vault is operationally heavy** for customers without it. Running highly-available Vault adds a tier of complexity.
- **Cross-cloud key migration** between adapters is non-trivial. Customers who pick KMS then want Vault need a migration plan.
- **FIPS 140-3 compliance differs.** Vault Enterprise has FIPS 140-2/3 modules; OSS Vault does not. Cloud KMS is FIPS-certified per cloud (AWS KMS = FIPS 140-2 Level 2; AWS CloudHSM = Level 3). Customer requirements drive the choice.

### Mitigations

- Define the `KeyCustody` protocol to be **minimal**: sign(data, key_id), verify(sig, data, key_id), encrypt(data, key_id), decrypt(ciphertext, key_id), rotate(key_id), erase(key_id). No leaky abstractions; adapters can be reasoned about independently.
- Write **portable key-export-and-import tooling** under `tools/key_migration.py` so adapter switches are tractable.
- Document **FIPS posture per adapter** in `docs/12_compliance_and_audit/COMPLIANCE_AND_AUDIT.md` so customers can pick based on their regulatory exposure.

## Alternatives considered

1. **Cloud KMS only** (no Vault). Rejected because customers running multi-cloud or on-premise can't use any one cloud KMS uniformly. Forces them into per-cloud key custody silos.
2. **Vault only** (no cloud KMS adapter). Rejected because Verixa would impose a new operational dependency on customers who already operate cloud KMS competently.
3. **In-app key custody backed by encrypted-at-rest disk** (e.g. age-encrypted key files). Rejected for compromise-resistance — process compromise reveals keys.
4. **TPM / HSM-only.** Deferred to Phase 3 (TEE-backed reviewer triad ADR will revisit hardware key custody for the reviewer-private-keys case).
5. **Wrap Phase 0 in-process keys with a master KEK from cloud KMS, keep DEKs in-process.** Considered. Rejected because BR-05 erasure semantics get murky — destroying a DEK in-process doesn't survive an attacker who already exfiltrated the in-process memory.

## Verification

- Phase 1 must demonstrate at least one design-partner customer running Vault-backed custody and one running cloud-KMS-backed custody.
- BR-05 cryptographic erasure must work end-to-end against both adapters.
- Per-call signing latency must be under 50ms p95 (Vault Transit is typically 10-30ms; KMS varies).
- Audit log must record key-use events with sufficient detail to reconstruct "which tenant's data was decrypted by whom when".

## Related

- ADR-0004 (Ed25519 over RSA) — the key algorithm choice; ADR-0008 is the key custody choice
- ADR-0007 (SPIRE auth) — Vault Agent auto-auth uses SPIRE attestation
- BR-05 (cryptographic erasure)
- `docs/10_security_architecture/SECURITY_ARCHITECTURE.md` — broader key management context
- `docs/12_compliance_and_audit/COMPLIANCE_AND_AUDIT.md` — FIPS posture documentation
- Phase 0 in-process key generation in `apps/runtime/verixa_runtime/crypto/key_bootstrap.py`
