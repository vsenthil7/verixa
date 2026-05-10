"""pytest suite for tools/audit_verify.py — offline CLI integrity check.

100% line + branch coverage on the CLI module. The
`if __name__ == '__main__'` line is `pragma: no cover` (standard).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from verixa_runtime.audit.emitter import AuditEmitInput, emit_audit_record
from verixa_runtime.audit.verifier import PersistedAuditEntry
from verixa_runtime.crypto.key_bootstrap import bootstrap_tenant


REPO_ROOT = Path(__file__).resolve().parents[3]
CLI_PATH = REPO_ROOT / "tools" / "audit_verify.py"


@pytest.fixture(scope="module")
def cli_module() -> ModuleType:
    """Load tools/audit_verify.py as a module so we can call main() directly."""
    spec = importlib.util.spec_from_file_location(
        "audit_verify_cli", CLI_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_verify_cli"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tenant_id() -> uuid.UUID:
    return uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _build_chain_export(
    tenant_id: uuid.UUID, length: int
) -> tuple[dict[str, Any], list[PersistedAuditEntry]]:
    """Return (export_dict, parallel_persisted_list_for_tampering_helpers)."""
    bundle = bootstrap_tenant(tenant_id)
    persisted: list[PersistedAuditEntry] = []
    prev: bytes | None = None
    base_time = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
    for seq in range(length):
        emit_in = AuditEmitInput(
            tenant_id=tenant_id,
            sequence_number=seq,
            event_time=base_time,
            workflow_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            agent_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            action_type="tool_call",
            decision="allow",
            risk_score=Decimal("0.250"),
            snapshot_hash=bytes([seq]) * 32,
            signing_private_key=bundle.signing_keypair.private_key,
            signing_key_id=bundle.signing_key_id,
            prev_self_hash=prev,
        )
        rec = emit_audit_record(emit_in)
        persisted.append(
            PersistedAuditEntry(
                tenant_id=rec.tenant_id,
                sequence_number=rec.sequence_number,
                event_time=rec.event_time,
                workflow_id=rec.workflow_id,
                agent_id=rec.agent_id,
                action_type=rec.action_type,
                decision=rec.decision,
                risk_score=rec.risk_score,
                snapshot_hash=rec.snapshot_hash,
                hash_chain_prev=rec.hash_chain_prev,
                hash_chain_self=rec.hash_chain_self,
                signature=rec.signature,
                signing_key_id=rec.signing_key_id,
                public_key=bundle.public_key,
            )
        )
        prev = rec.hash_chain_self

    export = {
        "tenant_id": str(tenant_id),
        "entries": [
            {
                "tenant_id": str(p.tenant_id),
                "sequence_number": p.sequence_number,
                "event_time": p.event_time.isoformat(),
                "workflow_id": str(p.workflow_id),
                "agent_id": str(p.agent_id),
                "action_type": p.action_type,
                "decision": p.decision,
                "risk_score": str(p.risk_score),
                "snapshot_hash": p.snapshot_hash.hex(),
                "hash_chain_prev": p.hash_chain_prev.hex(),
                "hash_chain_self": p.hash_chain_self.hex(),
                "signature": p.signature.hex(),
                "signing_key_id": p.signing_key_id,
                "public_key": p.public_key.hex(),
            }
            for p in persisted
        ],
    }
    return export, persisted


@pytest.fixture
def write_export(tmp_path: Path) -> Callable[[dict[str, Any]], Path]:
    def _write(export: dict[str, Any]) -> Path:
        p = tmp_path / "export.json"
        p.write_text(json.dumps(export), encoding="utf-8")
        return p

    return _write


# ---------------------------------------------------------------------------
# load_export
# ---------------------------------------------------------------------------


def test_load_export_happy(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
) -> None:
    export, _ = _build_chain_export(tenant_id, 2)
    p = write_export(export)
    tid, entries = cli_module.load_export(p)
    assert tid == tenant_id
    assert len(entries) == 2
    assert entries[0].sequence_number == 0


def test_load_export_rejects_non_object(
    cli_module: ModuleType, tmp_path: Path
) -> None:
    p = tmp_path / "x.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be a JSON object"):
        cli_module.load_export(p)


def test_load_export_rejects_missing_keys(
    cli_module: ModuleType, tmp_path: Path
) -> None:
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"tenant_id": str(uuid.uuid4())}), encoding="utf-8")
    with pytest.raises(ValueError, match="must contain 'tenant_id' and 'entries'"):
        cli_module.load_export(p)


def test_load_export_rejects_non_list_entries(
    cli_module: ModuleType, tmp_path: Path
) -> None:
    p = tmp_path / "x.json"
    p.write_text(
        json.dumps({"tenant_id": str(uuid.uuid4()), "entries": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="'entries' must be a list"):
        cli_module.load_export(p)


def test_load_export_rejects_bad_hex(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
) -> None:
    export, _ = _build_chain_export(tenant_id, 1)
    export["entries"][0]["snapshot_hash"] = "ZZ" * 32  # not hex
    p = write_export(export)
    with pytest.raises(ValueError, match="not valid hex"):
        cli_module.load_export(p)


def test_load_export_rejects_wrong_byte_length(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
) -> None:
    export, _ = _build_chain_export(tenant_id, 1)
    export["entries"][0]["public_key"] = "ab" * 16  # 16 bytes, want 32
    p = write_export(export)
    with pytest.raises(ValueError, match="expected 32 bytes"):
        cli_module.load_export(p)


# ---------------------------------------------------------------------------
# main() — exit codes + output
# ---------------------------------------------------------------------------


def test_main_returns_0_on_valid_chain(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    export, _ = _build_chain_export(tenant_id, 3)
    p = write_export(export)
    assert cli_module.main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "verified 3 entries" in out


def test_main_quiet_suppresses_success_output(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    export, _ = _build_chain_export(tenant_id, 1)
    p = write_export(export)
    assert cli_module.main([str(p), "--quiet"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_main_returns_1_on_missing_file(
    cli_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    missing = tmp_path / "does-not-exist.json"
    assert cli_module.main([str(missing)]) == 1
    err = capsys.readouterr().err
    assert "export file not found" in err


def test_main_quiet_suppresses_missing_file_message(
    cli_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    missing = tmp_path / "does-not-exist.json"
    assert cli_module.main([str(missing), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert err == ""


def test_main_returns_1_on_parse_error(
    cli_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    assert cli_module.main([str(p)]) == 1
    err = capsys.readouterr().err
    assert "could not parse export" in err


def test_main_quiet_suppresses_parse_error(
    cli_module: ModuleType,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    assert cli_module.main([str(p), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert err == ""


def test_main_returns_1_on_tampered_chain(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    export, _ = _build_chain_export(tenant_id, 2)
    # Tamper: flip a content field on entry 1 without recomputing self-hash
    export["entries"][1]["decision"] = "deny"
    p = write_export(export)
    assert cli_module.main([str(p)]) == 1
    err = capsys.readouterr().err
    assert "self-hash mismatch" in err


def test_main_quiet_suppresses_tamper_message(
    cli_module: ModuleType,
    tenant_id: uuid.UUID,
    write_export: Callable[[dict[str, Any]], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    export, _ = _build_chain_export(tenant_id, 2)
    export["entries"][1]["decision"] = "deny"
    p = write_export(export)
    assert cli_module.main([str(p), "--quiet"]) == 1
    err = capsys.readouterr().err
    assert err == ""
