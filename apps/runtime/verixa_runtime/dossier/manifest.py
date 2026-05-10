"""Dossier manifest assembly + signing (CP-13.1 / 13.2).

A DossierManifest is the per-decision JSON artifact handed to an
auditor. It contains four sections:

  1. **cover** -- which tenant, which decision, when, who.
  2. **decision_trail** -- risk score, classification, policies
     applied, triad outcome.
  3. **evidence** -- retrieved-document fingerprints, citations,
     tool I/O.
  4. **crypto_proof** -- storage_key for the encrypted replay
     bundle (third party can fetch + verify), audit ledger row
     reference, schema_version, signing_key_id of the Ed25519 key
     used to sign this manifest.

A SignedDossier wraps a DossierManifest with an Ed25519 signature
over canonicalise_manifest(manifest). The verifier function does the
inverse: re-canonicalise, recompute, compare via constant-time check.

Offline verification: a third party with only the SignedDossier JSON
and the tenant's published public key can verify the manifest
without ever talking to Verixa. This is the trust anchor.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Final

from verixa_runtime.crypto.ed25519 import (
    Ed25519SignatureError,
    sign as ed25519_sign,
    verify as ed25519_verify,
)
from verixa_runtime.replay.bundle import ReplayBundle


# Bumped when manifest schema changes incompatibly. Verifier refuses
# unknown versions so a Phase-1 manifest can't be silently
# misinterpreted as Phase-0.
DOSSIER_SCHEMA_VERSION: Final[int] = 1


class DossierManifestError(ValueError):
    """Raised on malformed manifest input or signature verification failure."""


@dataclass(frozen=True, slots=True)
class DossierManifest:
    """The unsigned manifest. Build via build_manifest()."""

    audit_id: uuid.UUID
    tenant_id: uuid.UUID
    generated_at_unix_ns: int

    # Cover
    decision: str  # "allow" / "deny" / "escalate"
    risk_score: float
    risk_classification: str  # "low" / "medium" / "high" / "critical"
    action_summary: str

    # Decision trail
    policy_evaluations: tuple[
        tuple[str, str, str], ...
    ] = field(default_factory=tuple)
    # Each: (package, decision, reason)
    triad_consensus: str | None = None
    triad_agreed_decision: str | None = None
    triad_dissenters: tuple[str, ...] = field(default_factory=tuple)

    # Evidence
    retrieved_documents: tuple[
        tuple[str, str], ...
    ] = field(default_factory=tuple)
    # Each: (doc_id, content_sha256_hex)

    # Crypto proof
    replay_storage_key: str = ""
    signing_key_id: str = ""

    schema_version: int = DOSSIER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.decision not in ("allow", "deny", "escalate"):
            raise DossierManifestError(
                f"decision must be allow/deny/escalate; "
                f"got {self.decision!r}"
            )
        if not 0.0 <= self.risk_score <= 1.0:
            raise DossierManifestError(
                f"risk_score must be in [0.0, 1.0]; got {self.risk_score!r}"
            )
        if self.risk_classification not in (
            "low", "medium", "high", "critical"
        ):
            raise DossierManifestError(
                f"risk_classification must be one of "
                f"low/medium/high/critical; got {self.risk_classification!r}"
            )
        if self.generated_at_unix_ns < 0:
            raise DossierManifestError(
                f"generated_at_unix_ns must be non-negative; "
                f"got {self.generated_at_unix_ns!r}"
            )
        if self.schema_version != DOSSIER_SCHEMA_VERSION:
            raise DossierManifestError(
                f"schema_version must be {DOSSIER_SCHEMA_VERSION}; "
                f"got {self.schema_version!r}"
            )


@dataclass(frozen=True, slots=True)
class SignedDossier:
    """DossierManifest + Ed25519 signature over its canonical bytes."""

    manifest: DossierManifest
    signature_hex: str  # 128-char lowercase hex (64-byte sig)
    public_key_hex: str  # 64-char lowercase hex (32-byte key)

    def __post_init__(self) -> None:
        if len(self.signature_hex) != 128:
            raise DossierManifestError(
                f"signature_hex must be 128 hex chars (64 bytes); "
                f"got {len(self.signature_hex)}"
            )
        if len(self.public_key_hex) != 64:
            raise DossierManifestError(
                f"public_key_hex must be 64 hex chars (32 bytes); "
                f"got {len(self.public_key_hex)}"
            )


def build_manifest(
    *,
    bundle: ReplayBundle,
    replay_storage_key: str,
    signing_key_id: str,
    generated_at_unix_ns: int,
    action_summary: str,
) -> DossierManifest:
    """Assemble a DossierManifest from a snapshotted ReplayBundle.

    The bundle carries the raw decision context; this function
    projects it into the auditor-facing manifest shape. The caller
    supplies the storage_key (where the encrypted bundle lives) and
    the signing_key_id (which Ed25519 key will sign the manifest).
    """
    # Risk classification: map score thresholds to category. Mirrors
    # risk.router.classify_risk but kept local so the dossier module
    # doesn't import the risk module (one-way dependency).
    if bundle.risk_score >= 0.80:
        risk_class = "critical"
    elif bundle.risk_score >= 0.50:
        risk_class = "high"
    elif bundle.risk_score >= 0.20:
        risk_class = "medium"
    else:
        risk_class = "low"

    policy_rows = tuple(
        (p.package, p.decision, p.reason) for p in bundle.policy_evaluations
    )

    triad_consensus: str | None = None
    triad_agreed: str | None = None
    triad_dissent: tuple[str, ...] = ()
    if bundle.triad_review is not None:
        triad_consensus = bundle.triad_review.consensus_kind
        triad_agreed = bundle.triad_review.agreed_decision
        # Dissenters: reviewer_ids whose decision differs from
        # the agreed_decision (for MAJORITY consensus). Phase-0
        # computes this from the verdicts tuple.
        if triad_agreed is not None:
            triad_dissent = tuple(
                rid for rid, dec, _conf, _reas in bundle.triad_review.verdicts
                if dec != triad_agreed
            )

    return DossierManifest(
        audit_id=bundle.audit_id,
        tenant_id=bundle.tenant_id,
        generated_at_unix_ns=generated_at_unix_ns,
        decision=bundle.decision,
        risk_score=bundle.risk_score,
        risk_classification=risk_class,
        action_summary=action_summary,
        policy_evaluations=policy_rows,
        triad_consensus=triad_consensus,
        triad_agreed_decision=triad_agreed,
        triad_dissenters=triad_dissent,
        retrieved_documents=bundle.retrieved_documents,
        replay_storage_key=replay_storage_key,
        signing_key_id=signing_key_id,
    )


def canonicalise_manifest(manifest: DossierManifest) -> bytes:
    """Deterministic JSON-bytes serialisation.

    This is what gets signed and what the offline verifier
    recanonicalises before checking the signature.
    """
    payload = {
        "schema_version": manifest.schema_version,
        "audit_id": str(manifest.audit_id),
        "tenant_id": str(manifest.tenant_id),
        "generated_at_unix_ns": manifest.generated_at_unix_ns,
        "decision": manifest.decision,
        "risk_score": manifest.risk_score,
        "risk_classification": manifest.risk_classification,
        "action_summary": manifest.action_summary,
        "policy_evaluations": [
            {"package": pkg, "decision": dec, "reason": rsn}
            for pkg, dec, rsn in manifest.policy_evaluations
        ],
        "triad_consensus": manifest.triad_consensus,
        "triad_agreed_decision": manifest.triad_agreed_decision,
        "triad_dissenters": list(manifest.triad_dissenters),
        "retrieved_documents": [
            {"doc_id": did, "content_sha256": sha}
            for did, sha in manifest.retrieved_documents
        ],
        "replay_storage_key": manifest.replay_storage_key,
        "signing_key_id": manifest.signing_key_id,
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_manifest(
    manifest: DossierManifest,
    *,
    private_key: bytes,
    public_key: bytes,
) -> SignedDossier:
    """Sign the canonicalised manifest with the tenant's Ed25519 key.

    Returns a SignedDossier carrying the manifest, the signature as
    lowercase hex, and the public key as lowercase hex (so the
    offline verifier doesn't need a separate key-distribution
    channel for the simple case).
    """
    payload = canonicalise_manifest(manifest)
    sig = ed25519_sign(private_key, payload)
    return SignedDossier(
        manifest=manifest,
        signature_hex=sig.hex(),
        public_key_hex=public_key.hex(),
    )


def verify_signed_dossier(signed: SignedDossier) -> None:
    """Re-canonicalise + verify the Ed25519 signature.

    Raises DossierManifestError on signature failure (wrapping the
    underlying Ed25519SignatureError so callers don't need to
    import the crypto module).
    """
    payload = canonicalise_manifest(signed.manifest)
    try:
        signature_bytes = bytes.fromhex(signed.signature_hex)
        public_key_bytes = bytes.fromhex(signed.public_key_hex)
    except ValueError as e:
        raise DossierManifestError(
            f"signature_hex or public_key_hex is not valid hex: {e!s}"
        ) from e
    try:
        ed25519_verify(public_key_bytes, payload, signature_bytes)
    except Ed25519SignatureError as e:
        raise DossierManifestError(
            f"dossier signature failed verification: {e!s}"
        ) from e
