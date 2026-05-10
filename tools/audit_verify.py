"""Offline audit-chain integrity verifier (standalone CLI).

Reads a JSON export of `verixa_audit.audit_entries` (joined with
`verixa_audit.signing_keys` so each row carries its `public_key`) and
walks the chain via `verify_audit_chain`.

The export format is documented in docs/09_evidence_pack_spec/
EVIDENCE_PACK_SPECIFICATION.md §2.1; CP-13 ships a generator. This CLI
is the consumer side: it can be run by an external auditor with no
network access to the Verixa runtime — only the JSON file is needed.

Export JSON shape:

    {
        "tenant_id": "<uuid>",
        "entries": [
            {
                "tenant_id": "<uuid>",
                "sequence_number": 0,
                "event_time": "<ISO-8601>",
                "workflow_id": "<uuid>",
                "agent_id": "<uuid>",
                "action_type": "...",
                "decision": "allow|deny|escalate|pending",
                "risk_score": "0.250",
                "snapshot_hash": "<hex>",
                "hash_chain_prev": "<hex>",
                "hash_chain_self": "<hex>",
                "signature": "<hex>",
                "signing_key_id": "verixa-sig-...",
                "public_key": "<hex>"
            },
            ...
        ]
    }

Exit codes:
    0  — chain verified
    1  — verification failed (or input error)
    2  — usage error
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from verixa_runtime.audit.verifier import (
    AuditVerificationError,
    PersistedAuditEntry,
    verify_audit_chain,
)


def _hex_to_bytes(value: str, *, expected_len: int, field: str) -> bytes:
    try:
        b = bytes.fromhex(value)
    except ValueError as e:
        raise ValueError(f"{field}: not valid hex") from e
    if len(b) != expected_len:
        raise ValueError(
            f"{field}: expected {expected_len} bytes, got {len(b)}"
        )
    return b


def _entry_from_json(obj: dict) -> PersistedAuditEntry:
    return PersistedAuditEntry(
        tenant_id=uuid.UUID(obj["tenant_id"]),
        sequence_number=int(obj["sequence_number"]),
        event_time=datetime.fromisoformat(obj["event_time"]),
        workflow_id=uuid.UUID(obj["workflow_id"]),
        agent_id=uuid.UUID(obj["agent_id"]),
        action_type=str(obj["action_type"]),
        decision=str(obj["decision"]),
        risk_score=Decimal(str(obj["risk_score"])),
        snapshot_hash=_hex_to_bytes(
            obj["snapshot_hash"], expected_len=32, field="snapshot_hash"
        ),
        hash_chain_prev=_hex_to_bytes(
            obj["hash_chain_prev"], expected_len=32, field="hash_chain_prev"
        ),
        hash_chain_self=_hex_to_bytes(
            obj["hash_chain_self"], expected_len=32, field="hash_chain_self"
        ),
        signature=_hex_to_bytes(
            obj["signature"], expected_len=64, field="signature"
        ),
        signing_key_id=str(obj["signing_key_id"]),
        public_key=_hex_to_bytes(
            obj["public_key"], expected_len=32, field="public_key"
        ),
    )


def load_export(path: Path) -> tuple[uuid.UUID, list[PersistedAuditEntry]]:
    """Parse an export JSON file. Raises ValueError on malformed input."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("export root must be a JSON object")
    if "tenant_id" not in raw or "entries" not in raw:
        raise ValueError("export must contain 'tenant_id' and 'entries' keys")
    tenant_id = uuid.UUID(raw["tenant_id"])
    entries_raw = raw["entries"]
    if not isinstance(entries_raw, list):
        raise ValueError("'entries' must be a list")
    entries = [_entry_from_json(e) for e in entries_raw]
    return tenant_id, entries


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code."""
    parser = argparse.ArgumentParser(
        prog="verixa-audit-verify",
        description=(
            "Offline integrity check for a Verixa audit-ledger export. "
            "Walks the hash chain end-to-end and verifies every signature."
        ),
    )
    parser.add_argument(
        "export_path",
        type=Path,
        help="Path to a JSON export of audit entries + signing keys.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success/failure messages; rely on exit code.",
    )
    args = parser.parse_args(argv)

    if not args.export_path.is_file():
        if not args.quiet:
            print(
                f"[FAIL] export file not found: {args.export_path}",
                file=sys.stderr,
            )
        return 1

    try:
        tenant_id, entries = load_export(args.export_path)
    except (ValueError, KeyError, TypeError) as e:
        if not args.quiet:
            print(f"[FAIL] could not parse export: {e}", file=sys.stderr)
        return 1

    try:
        verify_audit_chain(entries, tenant_id)
    except AuditVerificationError as e:
        if not args.quiet:
            print(f"[FAIL] {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(
            f"[OK] verified {len(entries)} entries for tenant {tenant_id}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
