"""Tenant key-bootstrap utility — dev mode for hackathon Phase 0.

Generates the per-tenant cryptographic material Verixa needs at onboarding:

  - Ed25519 signing keypair (audit-ledger signatures)
  - AES-256 data encryption key (replay-vault snapshots)
  - Stable string `signing_key_id` identifying the keypair in the
    `verixa_audit.signing_keys` table

Production deployments: private material is held in HashiCorp Vault
(transit engine for signing, KV for the replay DEK encrypted under a
per-tenant KEK). Public Ed25519 keys are persisted to Postgres. Verixa's
runtime never sees private bytes; it calls Vault to sign.

Hackathon dev mode: this module returns a `TenantKeyBundle` with private
bytes in-memory; the caller is responsible for writing them to a Vault
dev instance or a local secrets directory.

Public API:
  - `TenantKeyBundle`     — frozen dataclass with all generated material
  - `bootstrap_tenant`    — generate a fresh bundle for a tenant
  - `derive_signing_key_id` — stable id for (tenant_id, public_key) tuple
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from verixa_runtime.crypto.aes_gcm import AesGcmKey, generate_key
from verixa_runtime.crypto.ed25519 import Ed25519KeyPair, generate_keypair


def derive_signing_key_id(tenant_id: uuid.UUID, public_key: bytes) -> str:
    """Stable signing-key-id derived from (tenant_id, public_key).

    Format: ``"verixa-sig-<short-hash>"`` where short-hash is the first 16
    hex chars of SHA-256(tenant_id.bytes || public_key). Stable across
    process restarts; collision resistance ~64 bits within a tenant.
    """
    if not isinstance(tenant_id, uuid.UUID):
        raise TypeError(
            f"tenant_id must be uuid.UUID, got {type(tenant_id).__name__}"
        )
    if len(public_key) != 32:
        raise ValueError(
            f"public_key must be 32 bytes (Ed25519), got {len(public_key)}"
        )
    digest = hashlib.sha256(tenant_id.bytes + public_key).hexdigest()
    return f"verixa-sig-{digest[:16]}"


@dataclass(frozen=True, slots=True)
class TenantKeyBundle:
    """All cryptographic material generated for a tenant at onboarding."""

    tenant_id: uuid.UUID
    signing_keypair: Ed25519KeyPair
    signing_key_id: str
    replay_dek: AesGcmKey

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, uuid.UUID):
            raise TypeError("tenant_id must be uuid.UUID")
        if not self.signing_key_id.startswith("verixa-sig-"):
            raise ValueError(
                "signing_key_id must start with 'verixa-sig-'"
            )

    @property
    def public_key(self) -> bytes:
        """Convenience accessor for the public Ed25519 bytes."""
        return self.signing_keypair.public_key


def bootstrap_tenant(tenant_id: uuid.UUID) -> TenantKeyBundle:
    """Generate a complete fresh key bundle for `tenant_id`."""
    if not isinstance(tenant_id, uuid.UUID):
        raise TypeError(
            f"tenant_id must be uuid.UUID, got {type(tenant_id).__name__}"
        )
    kp = generate_keypair()
    sig_id = derive_signing_key_id(tenant_id, kp.public_key)
    dek = generate_key()
    return TenantKeyBundle(
        tenant_id=tenant_id,
        signing_keypair=kp,
        signing_key_id=sig_id,
        replay_dek=dek,
    )
