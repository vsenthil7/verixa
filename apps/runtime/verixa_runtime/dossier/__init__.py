"""Verixa Compliance Dossier Generator.

Produces per-decision evidence packs for auditors and regulators.

Phase-0 ships:
  - Per-decision dossier (one governed action -> one dossier)
  - JSON manifest with cover + decision trail + evidence + crypto proof
  - Ed25519 signature over the canonicalised manifest
  - Offline verifier (CLI script) that re-verifies the signature
    without needing the live Verixa runtime

Phase-1 extensions (not in Phase-0):
  - Per-workflow rolling dossier (last N decisions)
  - EU AI Act Annex IV technical-dossier shape
  - GDPR Article 72 incident-pack shape
  - PDF rendering (WeasyPrint or Playwright -- thin layer over the
    JSON manifest)

The dossier is the bridge between Verixa's internal representation
(ReplayBundle + audit ledger row) and a human-readable artifact a
non-engineer can inspect. Every claim in the dossier is backed by a
cryptographically verifiable pointer: storage_key for the encrypted
replay bundle, audit_id for the ledger row, signature for the
manifest itself.
"""

from verixa_runtime.dossier.manifest import (  # noqa: F401
    DOSSIER_SCHEMA_VERSION,
    DossierManifest,
    DossierManifestError,
    SignedDossier,
    build_manifest,
    canonicalise_manifest,
    sign_manifest,
    verify_signed_dossier,
)


__all__ = [
    "DOSSIER_SCHEMA_VERSION",
    "DossierManifest",
    "DossierManifestError",
    "SignedDossier",
    "build_manifest",
    "canonicalise_manifest",
    "sign_manifest",
    "verify_signed_dossier",
]
