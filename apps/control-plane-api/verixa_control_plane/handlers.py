"""Control Plane handlers for replay + dossier endpoints (CP-14.2).

Read-path handlers: take typed request envelopes, look up data via
existing runtime modules (Reconstructor from CP-12.4, build_manifest
+ sign_manifest from CP-13.1/13.2), return typed response envelopes.

Errors are returned as ErrorResponse envelopes paired with an HTTP
status code via the (status, body) tuple convention. CP-14.5 will
wrap this into FastAPI by mapping the tuple to a JSONResponse.

The dossier flow is two-step:
  1. POST /v1/control/dossier with an audit_id
     -> generates manifest, signs, stores under a fresh dossier_id,
        returns DossierGenerateResponse (thin -- just the id).
  2. GET /v1/control/dossier/{dossier_id}
     -> returns the full SignedDossier inline as DossierGetResponse.

The two-step shape matches how real auditors work: the operator
clicks "generate" once, then shares the GET URL with the auditor;
the auditor can verify offline using the inline signature + public
key without ever pinging back to Verixa.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from datetime import UTC
from typing import Protocol

from verixa_runtime.crypto.aes_gcm import AesGcmDecryptionError
from verixa_runtime.crypto.ed25519 import Ed25519KeyPair
from verixa_runtime.dossier import (
    SignedDossier,
    build_manifest,
    canonicalise_manifest,
    sign_manifest,
)
from verixa_runtime.replay import (
    BundleNotFound,
    Reconstructor,
    ReplayBundle,
)
from verixa_runtime.replay.snapshotter import AuditIndexMiss

from verixa_control_plane.envelopes import (
    DossierGenerateRequest,
    DossierGenerateResponse,
    DossierGetResponse,
    ErrorResponse,
    ReplayRequest,
    ReplayResponse,
)

# ---------------------------------------------------------------------------
# Dossier-store interface (Phase-0: in-memory)
# ---------------------------------------------------------------------------


class DossierStoreMiss(KeyError):
    """Raised when dossier_id is unknown to the DossierStore."""


class DossierStore(Protocol):
    """Maps dossier_id -> SignedDossier.

    Phase-0: InMemoryDossierStore. Phase-1: PostgresDossierStore
    backed by verixa_dossier.signed_dossier schema.
    """

    async def put(
        self, dossier_id: uuid.UUID, signed: SignedDossier
    ) -> None:  # pragma: no cover -- Protocol method body
        ...

    async def get(
        self, dossier_id: uuid.UUID
    ) -> SignedDossier:  # pragma: no cover -- Protocol method body
        ...


class InMemoryDossierStore:
    """Dict-backed DossierStore for tests and offline demo."""

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, SignedDossier] = {}
        self._lock = asyncio.Lock()

    async def put(
        self, dossier_id: uuid.UUID, signed: SignedDossier
    ) -> None:
        async with self._lock:
            self._items[dossier_id] = signed

    async def get(self, dossier_id: uuid.UUID) -> SignedDossier:
        async with self._lock:
            try:
                return self._items[dossier_id]
            except KeyError as e:
                raise DossierStoreMiss(
                    f"no dossier at dossier_id={dossier_id}"
                ) from e


# ---------------------------------------------------------------------------
# Translation: ReplayBundle -> ReplayResponse
# ---------------------------------------------------------------------------


def _bundle_to_replay_response(bundle: ReplayBundle) -> ReplayResponse:
    """Translate the domain bundle into the HTTP response envelope.

    Pure projection. Tuples become lists; nested frozen dataclasses
    become dicts. The shapes are stable across runtime + control
    plane because both reference the same envelope module.
    """
    triad: dict[str, object] | None
    if bundle.triad_review is None:
        triad = None
    else:
        triad = {
            "consensus_kind": bundle.triad_review.consensus_kind,
            "agreed_decision": bundle.triad_review.agreed_decision,
            "verdicts": [
                {
                    "reviewer_id": rid,
                    "decision": dec,
                    "confidence": conf,
                    "reasoning": reas,
                }
                for rid, dec, conf, reas in bundle.triad_review.verdicts
            ],
            "commitments": [
                {"reviewer_id": rid, "sha256_hex": h}
                for rid, h in bundle.triad_review.commitments
            ],
        }
    return ReplayResponse(
        audit_id=bundle.audit_id,
        tenant_id=bundle.tenant_id,
        decision=bundle.decision,
        risk_score=bundle.risk_score,
        request_envelope=bundle.request_envelope,
        retrieved_documents=[
            {"doc_id": did, "content_sha256": sha}
            for did, sha in bundle.retrieved_documents
        ],
        tool_io=list(bundle.tool_io),
        policy_evaluations=[
            {"package": p.package, "decision": p.decision, "reason": p.reason}
            for p in bundle.policy_evaluations
        ],
        triad_review=triad,
        timestamp_unix_ns=bundle.timestamp_unix_ns,
    )


# ---------------------------------------------------------------------------
# Replay handler
# ---------------------------------------------------------------------------


async def handle_replay(
    req: ReplayRequest,
    *,
    reconstructor: Reconstructor,
) -> tuple[int, ReplayResponse | ErrorResponse]:
    """POST /v1/control/replay handler.

    Returns (200, ReplayResponse) on success; (404, ErrorResponse)
    if the audit_id is unknown or the underlying ciphertext is gone;
    (500, ErrorResponse) on crypto failure (wrong key or tamper).
    """
    try:
        bundle = await reconstructor.reconstruct(req.audit_id)
    except AuditIndexMiss:
        return 404, ErrorResponse(
            error="audit_not_found",
            message=f"no replay entry indexed for audit_id={req.audit_id}",
            audit_id=req.audit_id,
        )
    except BundleNotFound:
        return 404, ErrorResponse(
            error="bundle_not_found",
            message=(
                "index pointed at a storage key the bundle store "
                "does not have (was the bundle physically deleted?)"
            ),
            audit_id=req.audit_id,
        )
    except AesGcmDecryptionError:
        return 500, ErrorResponse(
            error="bundle_decryption_failed",
            message=(
                "ciphertext authenticated incorrectly -- wrong tenant "
                "key, tamper, or AD mismatch"
            ),
            audit_id=req.audit_id,
        )
    return 200, _bundle_to_replay_response(bundle)


# ---------------------------------------------------------------------------
# Dossier-generate handler
# ---------------------------------------------------------------------------


async def handle_dossier_generate(
    req: DossierGenerateRequest,
    *,
    reconstructor: Reconstructor,
    dossier_store: DossierStore,
    signing_keypair: Ed25519KeyPair,
    signing_key_id: str,
    replay_storage_key_resolver: Callable[[uuid.UUID], str] | None = None,
    generated_at_unix_ns: int | None = None,
) -> tuple[int, DossierGenerateResponse | ErrorResponse]:
    """POST /v1/control/dossier handler.

    Workflow:
      1. Reconstruct the ReplayBundle for the audit_id.
      2. Resolve the replay_storage_key (from the audit index) so
         the manifest's crypto_proof section points at the encrypted
         bundle bytes.
      3. Build + sign the manifest with the supplied Ed25519 keypair.
      4. Store the SignedDossier under a fresh dossier_id.
      5. Return the thin DossierGenerateResponse.

    ``replay_storage_key_resolver`` is optional: if None, the
    handler falls back to using the audit_id as the placeholder
    pointer (sufficient for the Phase-0 in-memory demo where the
    audit_id is sufficient to refetch). Production passes a
    function that consults the audit ledger.

    ``generated_at_unix_ns`` is injectable for deterministic tests.
    """
    # Reconstruct.
    try:
        bundle = await reconstructor.reconstruct(req.audit_id)
    except AuditIndexMiss:
        return 404, ErrorResponse(
            error="audit_not_found",
            message=f"no replay entry indexed for audit_id={req.audit_id}",
            audit_id=req.audit_id,
        )
    except BundleNotFound:
        return 404, ErrorResponse(
            error="bundle_not_found",
            message="bundle store missing the ciphertext for this audit_id",
            audit_id=req.audit_id,
        )

    # Resolve replay storage key.
    if replay_storage_key_resolver is not None:
        replay_storage_key = replay_storage_key_resolver(req.audit_id)
    else:
        # Phase-0 fallback: use the audit_id hex as the pointer.
        # CP-14.5 wires the real resolver through dependency
        # injection from the app state.
        replay_storage_key = str(req.audit_id).replace("-", "") * 2

    # Build action summary: caller-supplied, else system-generated.
    action_summary = req.action_summary or _default_action_summary(bundle)

    # Build + sign manifest.
    ts = (
        generated_at_unix_ns
        if generated_at_unix_ns is not None
        else time.time_ns()
    )
    manifest = build_manifest(
        bundle=bundle,
        replay_storage_key=replay_storage_key,
        signing_key_id=signing_key_id,
        generated_at_unix_ns=ts,
        action_summary=action_summary,
    )
    signed = sign_manifest(
        manifest,
        private_key=signing_keypair.private_key,
        public_key=signing_keypair.public_key,
    )

    # Persist under a fresh dossier_id.
    dossier_id = uuid.uuid4()
    await dossier_store.put(dossier_id, signed)

    return 200, DossierGenerateResponse(
        dossier_id=dossier_id,
        audit_id=req.audit_id,
        signing_key_id=signing_key_id,
        generated_at=_ts_ns_to_datetime(ts),
    )


def _default_action_summary(bundle: ReplayBundle) -> str:
    """System-generated summary when caller passes empty action_summary.

    Phase-0: pull tool_name + decision out of the request envelope
    if available, fall back to a generic string.
    """
    action = bundle.request_envelope.get("action", {})
    if isinstance(action, dict):
        tool = action.get("tool_name") or action.get("type", "unknown")
        return f"{tool} ({bundle.decision})"
    return f"governed action ({bundle.decision})"


def _ts_ns_to_datetime(ts_ns: int):
    """Render nanoseconds-since-epoch as timezone-aware UTC datetime."""
    from datetime import datetime

    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=UTC)


# ---------------------------------------------------------------------------
# Dossier-get handler
# ---------------------------------------------------------------------------


async def handle_dossier_get(
    dossier_id: uuid.UUID,
    *,
    dossier_store: DossierStore,
) -> tuple[int, DossierGetResponse | ErrorResponse]:
    """GET /v1/control/dossier/{dossier_id} handler.

    Returns the full SignedDossier inline so the caller can verify
    the signature offline. (404, ErrorResponse) if unknown.
    """
    try:
        signed = await dossier_store.get(dossier_id)
    except DossierStoreMiss:
        return 404, ErrorResponse(
            error="dossier_not_found",
            message=f"no dossier at dossier_id={dossier_id}",
        )

    # Serialise the manifest as the dict shape DossierGetResponse
    # expects. Round-trip through canonicalise + json.loads to
    # guarantee the bytes the auditor verifies are the same bytes
    # the signature was over.
    import json
    manifest_dict = json.loads(canonicalise_manifest(signed.manifest))
    return 200, DossierGetResponse(
        dossier_id=dossier_id,
        audit_id=signed.manifest.audit_id,
        manifest=manifest_dict,
        signature_hex=signed.signature_hex,
        public_key_hex=signed.public_key_hex,
    )


__all__ = [
    "DossierStore",
    "DossierStoreMiss",
    "InMemoryDossierStore",
    "handle_dossier_generate",
    "handle_dossier_get",
    "handle_replay",
]
