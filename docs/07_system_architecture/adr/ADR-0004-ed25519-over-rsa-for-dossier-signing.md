# ADR-0004 — Ed25519 over RSA for dossier signing

- **Status:** Accepted
- **Date:** 2026-04-15
- **Phase:** 0 (hackathon prototype) — durable through Phase 1+
- **Decision owner:** v_sen
- **Affects:** Audit ledger signing, dossier signing, replay bundle sealing keys (separate AES-256-GCM key)

## Context

Verixa's evidence pack (`SignedDossier`) carries a digital signature over the canonical-JSON encoding of the manifest. The signature is the primary mechanism by which an external auditor verifies that:

1. The dossier was produced by Verixa (authenticity)
2. The dossier has not been modified since Verixa signed it (integrity)
3. The verification can be done **offline**, with no live call to Verixa

The choice of signature algorithm has long-term consequences: dossiers signed today must remain verifiable for the legally-mandated retention period (e.g. 7 years for some financial-services scenarios, longer for healthcare). Changing the algorithm later requires either re-signing the archive or running multiple verifiers.

The candidates are:

- **RSA-2048 / RSA-4096** with PKCS#1 v1.5 or PSS padding — the conventional choice
- **Ed25519** (EdDSA over Curve25519) — modern, fast, fixed-size signatures
- **ECDSA P-256 / P-384** — middle ground
- **Quantum-resistant signatures** (Dilithium, SPHINCS+) — not yet standardised broadly

## Decision

**Use Ed25519 for all Verixa signing operations** (audit ledger, dossier, policy bundles), via the `pynacl` library which wraps the audited `libsodium` implementation.

Concrete files:

- `apps/runtime/verixa_runtime/crypto/ed25519.py` — `SigningKey` / `VerifyKey` wrappers + helpers
- `apps/runtime/verixa_runtime/dossier/manifest.py` — uses Ed25519 to sign canonical-JSON manifests
- `apps/runtime/verixa_runtime/audit/emitter.py` — Ed25519 signs each ledger entry's hash-chain head
- `tools/audit_verify.py` — standalone offline verifier using only `pynacl` (`pip install pynacl` and the dossier JSON — nothing else)

Sealing keys for replay bundles use **AES-256-GCM with separate per-tenant keys** — see `apps/runtime/verixa_runtime/crypto/aes_gcm.py`. AES is a symmetric-encryption choice, not in tension with the Ed25519 signing choice.

## Consequences

### Positive

- **Fixed-size signatures** (64 bytes for Ed25519 vs 256+ bytes for RSA-2048). Dossiers are smaller, faster to transmit, and the signature field is always exactly 128 hex characters — easy to validate by length alone.
- **Fixed-size public keys** (32 bytes for Ed25519 vs 270+ bytes for RSA-2048 public key in DER). Easier to embed in dossiers, QR codes, or printable formats for air-gapped verification.
- **Fast verification** (~80 µs per signature on commodity hardware). Important because we expect auditors to verify thousands of dossiers in a batch.
- **No padding-oracle attacks.** Ed25519 has no PKCS#1 v1.5 / PSS variant choice; the algorithm is fully specified.
- **Deterministic signatures.** Same key + same message = same signature. Re-signing is idempotent; signature mismatches are unambiguous.
- **Excellent library support.** `pynacl` (Python), `crypto/ed25519` (Go), Node `crypto.sign()`, OpenSSL ≥ 1.1.1, Rust `ed25519-dalek`. An auditor can verify a Verixa dossier from any major language without licensing complications.
- **No "RSA key size selection" debate.** RSA-2048 is debatably borderline for 2026+ retention; RSA-4096 doubles signature size and triples verification time. Ed25519 has a single well-defined security level (~128-bit equivalent) and that's it.

### Negative

- **Less ubiquitous in legacy regulated industries.** Some banking and healthcare audit toolchains still expect RSA + X.509 PKI. Verixa's offline verifier does not require X.509; auditors who do require it can re-sign the public key with their existing PKI as an outer layer.
- **Not yet on every FIPS 140-3 certified module.** Ed25519 was added to FIPS 186-5 in 2023; certified module rollout is in progress. For Phase 1 deployments in FIPS-required environments, we may need to support an optional RSA-backed signing path. ADR placeholder filed.
- **Quantum-vulnerable** (as is RSA). Both will need to be replaced by a post-quantum scheme (e.g. ML-DSA / Dilithium) when those standardise. The dossier schema's `format_version` field is the migration anchor for that day.

### Mitigations

- The signed-bytes payload (canonical-JSON of the manifest) is **algorithm-independent** — switching to a different signing algorithm in Phase 2+ is a `signature_algorithm` field change + a new verifier path, with old dossiers verified by the old path. No data migration required.
- For Phase 1 FIPS deployments: Verixa's signing module accepts a pluggable `SigningKey` interface. A FIPS-mode build can substitute an HSM-backed RSA signer; the wire format updates the `signature_algorithm` field. No business-logic change.
- All Verixa-produced dossiers explicitly record `signature_algorithm: "ed25519"` in the manifest, so a verifier never has to guess.

## Alternatives considered

1. **RSA-2048** — rejected. Larger signatures + slower verification + padding-mode complexity. Not sufficient additional benefit for legacy interop in Phase 0.
2. **RSA-4096** — rejected. Signature size (512 bytes) hurts dossier portability; 5× slower verification.
3. **ECDSA P-256** — considered. Comparable performance to Ed25519 but with **non-deterministic signatures** (depend on a random nonce) — a buggy or compromised RNG produces catastrophic key-recovery (Sony PS3 incident, 2010). Ed25519's deterministic nonce derivation is safer. Rejected.
4. **Hybrid Ed25519 + RSA dual-signature** — considered. Defensible "belt and braces" approach, but doubles signature size and complicates verification. Filed as Phase 2 candidate for FIPS deployments.
5. **Post-quantum (Dilithium)** — too early. NIST PQC standards are still settling; library support is immature; signature size is ~2.4 KB. Phase 3+ candidate.

## Verification

- `packages/verixa-python/tests/test_crypto_ed25519.py` — unit tests for sign / verify / wrong-key rejection / tampered-payload rejection / deterministic-signature property
- `packages/verixa-python/tests/test_dossier_manifest.py` — `test_verify_signed_dossier_round_trip` proves end-to-end sign → serialise → deserialise → verify works
- `packages/verixa-python/tests/test_audit_verify_cli.py` — proves `tools/audit_verify.py` works as a standalone offline verifier with just `pynacl` installed
- Live HF Space smoke test (`_backup/smoke_test_hf_space.py`) asserts every fetched dossier has exactly 128-char `signature_hex` and 64-char `public_key_hex` — wire-format invariants

## Related

- BRD: BR-04 (offline dossier verification)
- Use case: UC-10 (offline dossier verification — Verixa NOT in trust path)
- NFR-02 (standard crypto only — no custom)
- Phase 1 candidate ADR: optional FIPS-mode RSA path
- Phase 3 candidate ADR: post-quantum migration when NIST PQC stabilises
