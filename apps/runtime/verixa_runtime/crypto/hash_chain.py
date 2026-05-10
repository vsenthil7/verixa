"""SHA-256 hash chain — audit-ledger integrity.

Per docs/06_data_model/DATA_MODEL.md §5.2:

    hash_chain_self = sha256(
        sequence_number || event_time || workflow_id || agent_id ||
        action_type || decision || risk_score ||
        snapshot_hash || hash_chain_prev
    )

Genesis (sequence_number == 0):
    hash_chain_prev = sha256(b"verixa-genesis-" || tenant_id)

This module is byte-deterministic. Every input is canonicalised to bytes
in a fixed order; identical inputs anywhere in the world produce
identical hashes.

Public API:
  - `HashChainEntry`            — frozen dataclass of canonical inputs
  - `HashChainBrokenError`      — raised by `verify_chain` on integrity failure
  - `compute_genesis_prev`      — genesis-hash for a tenant
  - `compute_self_hash`         — single-entry hash
  - `verify_chain`              — walk a list of entries from genesis
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

GENESIS_PREFIX: Final[bytes] = b"verixa-genesis-"
SHA256_BYTES: Final[int] = 32


class HashChainBrokenError(ValueError):
    """Raised when a hash-chain walk detects a broken or tampered chain."""


@dataclass(frozen=True, slots=True)
class HashChainEntry:
    """Canonical representation of a single audit-ledger row's chain inputs.

    All fields are required; nullable database columns must be normalised
    by the caller before constructing this dataclass (e.g. risk_score is
    ``Decimal("0.000")`` if absent in the DB row, not None).
    """

    sequence_number: int
    event_time: datetime
    workflow_id: uuid.UUID
    agent_id: uuid.UUID
    action_type: str
    decision: str
    risk_score: Decimal
    snapshot_hash: bytes
    hash_chain_prev: bytes

    def __post_init__(self) -> None:
        if self.sequence_number < 0:
            raise ValueError("sequence_number must be non-negative")
        if len(self.snapshot_hash) != SHA256_BYTES:
            raise ValueError(
                f"snapshot_hash must be {SHA256_BYTES} bytes (SHA-256 digest)"
            )
        if len(self.hash_chain_prev) != SHA256_BYTES:
            raise ValueError(
                f"hash_chain_prev must be {SHA256_BYTES} bytes (SHA-256 digest)"
            )


def compute_genesis_prev(tenant_id: uuid.UUID) -> bytes:
    """Compute the synthetic predecessor hash for sequence_number == 0.

    Definition: ``sha256("verixa-genesis-" || tenant_id.bytes)``.
    """
    if not isinstance(tenant_id, uuid.UUID):
        raise TypeError(
            f"tenant_id must be uuid.UUID, got {type(tenant_id).__name__}"
        )
    h = hashlib.sha256()
    h.update(GENESIS_PREFIX)
    h.update(tenant_id.bytes)
    return h.digest()


def _canonical_bytes(entry: HashChainEntry) -> bytes:
    """Concatenate the entry's chain inputs in fixed canonical order."""
    parts: list[bytes] = []
    # sequence_number — fixed-width 8-byte big-endian unsigned
    parts.append(entry.sequence_number.to_bytes(8, "big", signed=False))
    # event_time — ISO-8601 UTC with microseconds, byte-encoded
    parts.append(entry.event_time.isoformat().encode("utf-8"))
    # UUIDs — raw 16-byte form (not string)
    parts.append(entry.workflow_id.bytes)
    parts.append(entry.agent_id.bytes)
    # Strings — UTF-8 with explicit length prefix to prevent
    # action_type+decision concatenation ambiguity (e.g. "abc"+"de"
    # vs "ab"+"cde"). 4-byte big-endian length, then the bytes.
    for s in (entry.action_type, entry.decision):
        b = s.encode("utf-8")
        parts.append(len(b).to_bytes(4, "big", signed=False))
        parts.append(b)
    # risk_score — string form for cross-language reproducibility (Python
    # Decimal vs Postgres NUMERIC vs JS BigDecimal would otherwise differ).
    rs = format(entry.risk_score, "f")
    rs_b = rs.encode("utf-8")
    parts.append(len(rs_b).to_bytes(4, "big", signed=False))
    parts.append(rs_b)
    # 32-byte hashes — fixed width, no length prefix needed
    parts.append(entry.snapshot_hash)
    parts.append(entry.hash_chain_prev)
    return b"".join(parts)


def compute_self_hash(entry: HashChainEntry) -> bytes:
    """Compute `hash_chain_self` for a single entry. Returns 32 bytes."""
    return hashlib.sha256(_canonical_bytes(entry)).digest()


def verify_chain(
    entries: list[HashChainEntry],
    expected_self_hashes: list[bytes],
    tenant_id: uuid.UUID,
) -> None:
    """Walk a chain of entries from genesis; raise on any mismatch.

    Parameters
    ----------
    entries
        Entries in ascending `sequence_number` order. Must start at 0.
    expected_self_hashes
        For each entry, the `hash_chain_self` value previously stored
        in `verixa_audit.audit_entries.hash_chain_self`.
    tenant_id
        The tenant the chain belongs to (used to derive genesis_prev).
    """
    if len(entries) != len(expected_self_hashes):
        raise HashChainBrokenError(
            "entries and expected_self_hashes length mismatch: "
            f"{len(entries)} vs {len(expected_self_hashes)}"
        )
    if not entries:
        return  # empty chain is vacuously consistent

    # First entry must be at sequence_number == 0 with synthetic genesis prev.
    expected_prev = compute_genesis_prev(tenant_id)
    for index, (entry, expected_self) in enumerate(
        zip(entries, expected_self_hashes, strict=True)
    ):
        if entry.sequence_number != index:
            raise HashChainBrokenError(
                f"sequence gap at position {index}: expected "
                f"sequence_number={index}, got {entry.sequence_number}"
            )
        if entry.hash_chain_prev != expected_prev:
            raise HashChainBrokenError(
                f"prev-hash mismatch at sequence_number={entry.sequence_number}"
            )
        actual_self = compute_self_hash(entry)
        if actual_self != expected_self:
            raise HashChainBrokenError(
                f"self-hash mismatch at sequence_number={entry.sequence_number}"
            )
        expected_prev = actual_self  # advance the chain
